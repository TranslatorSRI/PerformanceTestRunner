import requests
import json
import os
import logging
import time
import argparse
import asyncio
import datetime
import httpx
import numpy as np
import ast
import traceback
from bs4 import BeautifulSoup
from copy import deepcopy
from typing import Any, Dict, List
from PerformanceTestRunner.smart_api_discover import SmartApiDiscover
from concurrent.futures import ThreadPoolExecutor

# We really shouldn't be doing this, but just for now...
from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
logging.basicConfig(filename="test_ars.log", level=logging.DEBUG)

BASE_PATH = os.path.dirname(os.path.realpath(__file__))
parser = argparse.ArgumentParser(description='Performance Load Testing')
parser.add_argument('--env', help='environment to run the analysis on', default='ci')
parser.add_argument('--count', help='number of queries to run concurrently', type=int)
parser.add_argument('--predicate',help='predicate',nargs="*",type=str)
parser.add_argument('--runner_setting', help='creative mode indicator',nargs="*", type=str)
parser.add_argument('--biolink_object_aspect_qualifier', help='activity_or_abundance', nargs="*",type=str)
parser.add_argument('--biolink_object_direction_qualifier', help='increased/decreased',nargs="*",type=str)
parser.add_argument('--input_category', help='Gene/ChemicalEntity', nargs="*",type=str)
parser.add_argument('--input_curie', help='Input Curie', nargs="*",type=str)
parser.add_argument('--component', help='ARS/ARAs/KPs', nargs="*",type=str)

env_spec = {
    'dev': 'ars-dev',
    'ci': 'ars.ci',
    'test': 'ars.test',
    'prod': 'ars-prod'
}
x_maturity = {
    'dev': 'development',
    'ci': 'staging',
    'test': 'testing',
    'prod': 'production'
}
urlSmartapi = "http://smart-api.info"
secsTimeout = 5

def get_safe(element, *keys):
    """
    :param element: JSON to be processed
    :param keys: list of keys in order to be traversed. e.g. "fields","data","message","results
    :return: the value of the terminal key if present or None if not
    """
    if element is None:
        return None
    _element = element
    for key in keys:
        try:
            _element = _element[key]
            if _element is None:
                return None
            if key == keys[-1]:
                return _element
        except KeyError:
            return None
    return None


async def get_children_info(rj:Dict[str,any], pk:str, input_id:str, ARS_URL:str):
    stragglers=[]
    query={}
    query[input_id]={}
    query[input_id]['actors']={}

    children = rj['children']
    for child in children:
        actor = child['actor']['agent']
        if child['status'] == 'Done':
            child_pk = str(child['message'])
            actor = child['actor']['agent']
            url = ARS_URL + "messages/" + child_pk
            async with httpx.AsyncClient(verify=False) as client:
                 r = await client.get(url,timeout=60)
            try:
                 rj = r.json()
            except json.decoder.JSONDecodeError:
                print(f"Non-JSON content received for pk: {child_pk}")
                print(r.text)

            timestamp = datetime.datetime.strptime(rj['fields']['timestamp'], '%Y-%m-%dT%H:%M:%S.%fZ')
            updated_at = datetime.datetime.strptime(rj['fields']['updated_at'], '%Y-%m-%dT%H:%M:%S.%fZ')
            completion_time = (updated_at - timestamp).total_seconds()
            if child['result_count'] is None:
                child['result_count'] = 0
        elif (child['status'] == 'Error' and child['code'] == 598) or (child['status'] == 'Running' and child['code'] == 202):
            if actor not in stragglers:
                stragglers.append(actor)
            else:
                 pass
            completion_time = None
        else:
            #print(f"child status is {child['status']} and child code is {child['code']}")
            completion_time = None
        query[input_id]['actors'][actor]={}
        query[input_id]['actors'][actor]['status'] = child['status']
        query[input_id]['actors'][actor]['n_results'] = child['result_count']
        query[input_id]['actors'][actor]['completion_time'] = completion_time

        if stragglers:
            query[input_id]['stragglers'] = stragglers
        query[input_id]['parent_pk'] = pk
    return query

def remove_knowledge_type(message_list):
    try:
        scrubbed_mesg_list=[]
        for mesg in message_list:
            edges = get_safe(mesg, 'message','query_graph','edges')
            for edge in edges.values():
                if 'knowledge_type' in edge.keys():
                    del edge['knowledge_type']
                    scrubbed_mesg_list.append(mesg)
    except Exception as e:
        print(e)

    return scrubbed_mesg_list
async def add_total_completion_time(queries:Dict[str,any]):
    # for query_list in queries.values():
    for item in queries:
        for file, parameter in item.items():
            for param_key, param_val in parameter.items():
                if param_key not in ['stragglers', 'parent_pk', 'merge_report']:
                    completion_list = []
                    for actor, actor_val in parameter[param_key].items():
                        if actor_val['completion_time'] is not None:
                            completion_list.append(actor_val['completion_time'])

                    completion_arr = np.array(completion_list)
                    max_completion=max(completion_arr)
                else:
                    pass
            item[file]['completion_time']=max_completion

    return queries
async def get_merged_info(rj:Dict[str,any], ARS_URL:str):
    merge_list = ast.literal_eval(rj["merged_versions_list"])
    query_merge={}
    if merge_list is not None:
        for merge_item in merge_list:
            merge_pk = merge_item[0]
            actor = merge_item[1]
            url = ARS_URL + "messages/" + merge_pk + "?trace=y"
            async with httpx.AsyncClient(verify=False) as client:
                r = await client.get(url,timeout=60)
            try:
                rj = r.json()
            except json.decoder.JSONDecodeError:
                print(f"Non-JSON content received for pk {merge_pk}")
                print(r.text)
            status = rj['status']
            timestamp = datetime.datetime.strptime(rj['timestamp'], '%Y-%m-%d %H:%M:%S.%f%z')
            updated_at = datetime.datetime.strptime(rj['updated_at'], '%Y-%m-%d %H:%M:%S.%f%z')
            completion_time = (updated_at - timestamp).total_seconds()
            query_merge[actor] = {}
            query_merge[actor]['status'] = status
            query_merge[actor]['merged_pk'] = merge_pk
            query_merge[actor]['completion_time'] = completion_time

    return query_merge

async def call_ars(payload: Dict[str,any],ARS_URL: str):
    url = ARS_URL+"submit"
    logging.debug("call_ars")
    async with httpx.AsyncClient(verify=False) as client:
        response = await client.post(
            url,
            json=payload,
            timeout=60,
        )
    response.raise_for_status()
    rj= response.json()
    pk = rj["pk"]
    return pk

async def call_ara(message_list: List[str], ARA_URLS_map: List[str]):
    report_card=[]
    ARA_report={}
    for agent, url in ARA_URLS_map.items():
        URL = url+"query"
        ARA_report[agent]=[]
        for mesg in message_list:
            try:
                async with httpx.AsyncClient(verify=False) as client:
                    response = await client.post(URL, json=mesg, timeout=300)
            except Exception as e:
                print(e)
            response.raise_for_status()
            rj= response.json()
            status = rj['status'] #success
            total_result = len(rj['message']['results'])
            completion_time = response.elapsed.total_seconds()
            ARA_report[agent].append([status,total_result,completion_time])
        report_card.append(ARA_report[agent])
    return report_card


async def generate(template: Dict[str,any],input_curie: str,aspect_qualifier: str,direction_qualifier: str,category: str):
    nodes = get_safe(template, "message", "query_graph", "nodes")
    edges = get_safe(template, "message", "query_graph", "edges")
    if aspect_qualifier == '' and direction_qualifier == '' and category == 'biolink:Disease':
        for node_val in nodes.values():
            if 'ids' in node_val:
                node_val['ids'].append(input_curie)
    else:
        if category == 'biolink:Gene':
            nodes['ON']['ids'].append(input_curie)
            del nodes['SN']['ids']
            edges['t_edge']['qualifier_constraints'][0]['qualifier_set'][0]['qualifier_value'] = aspect_qualifier
            edges['t_edge']['qualifier_constraints'][0]['qualifier_set'][1]['qualifier_value'] = direction_qualifier

        elif category == 'biolink:ChemicalEntity':
            nodes['SN']['ids'].append(input_curie)
            del nodes['ON']['ids']
            edges['t_edge']['qualifier_constraints'][0]['qualifier_set'][0]['qualifier_value'] = aspect_qualifier
            edges['t_edge']['qualifier_constraints'][0]['qualifier_set'][1]['qualifier_value'] = direction_qualifier
        else:
            template = {"error": f"unsupported input category provided: {category}"}

    return template

async def generate_message(predicate: List[str], creative: any,biolink_object_aspect_qualifier: List[str],biolink_object_direction_qualifier: List[str],input_category: List[str],input_curie: List[str]):
    """Create list of message queires ready to be sent to the Translator services"""
    query=[]
    template_dir = BASE_PATH + "/templates"

    #checking for correct input list lengths
    query_count = len(input_curie)
    if len(biolink_object_aspect_qualifier) != query_count or len(biolink_object_direction_qualifier) != query_count or len(input_category) != query_count or len(predicate) != query_count:
        query = [{"error": f"You have provided input lists of unequal lengths"}]
        return query

    for idx, input_curie in enumerate(input_curie):
        aspect_qualifier = biolink_object_aspect_qualifier[idx]
        direction_qualifier = biolink_object_direction_qualifier[idx]
        category = input_category[idx]
        pred = predicate[idx]
        if pred in ['treats','affects']:
            if creative:
                template_name = pred+'_creative'
            else:
                template_name = pred
        with open(template_dir+f'/{template_name}.json') as f:
            template = json.load(f)
            template = deepcopy(template)

        message = await generate(template,input_curie,aspect_qualifier,direction_qualifier,category)
        query.append(message)
    return query

async def smartapi_registry(map, component):
    agent_map={}
    for infores in map.keys():
        if infores == 'infores:ars' or infores == 'infores:workflow-runner': # or infores == 'infores:biothings-explorer':
            pass
        elif map[infores]['component'] == component:
            if infores != 'infores:text-mining-provider-cooccurrence':
                if map[infores]['urlServer'].endswith('/'):
                    agent_map[infores]=map[infores]['urlServer']+'query'
                else:
                    if 'answerappraiser' in map[infores]['urlServer']:
                        agent_map[infores]=map[infores]['urlServer']+'/get_appraisal'
                    elif 'nodenorm' in map[infores]['urlServer']:
                        agent_map[infores]=map[infores]['urlServer']+'/get_normalized_nodes'
                    else:
                        agent_map[infores]=map[infores]['urlServer']+'/query'

    return agent_map

def send_post_request(url, data):
    try:
        headers={'Content-Type': 'application/json', 'accept': 'application/json'}
        #print(f'sending mesg to url: {url} at {datetime.datetime.now()}')
        response = requests.post(url=url, headers=headers, json=data, timeout=360)
        # You can handle the response here
        print(f"Response from {url}: {response.status_code}")
        return response
    except requests.exceptions.ConnectionError as e:
        return e
    except requests.Timeout:
        print(f"Request timed out for {url}!")
        return None

def scrub_utility_list(utility_list, count):
    scrubed_list=[]
    for response in utility_list:
        agent_response = response[1]
        res=get_safe(agent_response,"message", "results")
        kg_nodes=get_safe(agent_response,"message","knowledge_graph","nodes")
        kg_edges=get_safe(agent_response,"message", "knowledge_graph","edges")
        try:
            if res is not None and kg_nodes is not None and kg_edges is not None:
                if isinstance(res, list) and len(res) != 0:
                    scrubed_list.append([response[0],{'message': response[1]['message']}])
        except Exception as e:
            print(e)
    scrubbed=scrubed_list[0:count]
    return scrubbed
def run_node_norm(url, indv_agent,indv_response):
    kg = get_safe(indv_response, "message", "knowledge_graph")
    nodes = kg['nodes']
    ids=list(nodes.keys())
    if len(ids)>0:
        j ={
            "curies":ids,
            "conflate":True,
            "drug_chemical_conflate":True
        }
        #print(f'sending nodes from {indv_agent} to url: {url} at {datetime.datetime.now()}')
        response = requests.post(url=url, data=json.dumps(j))

    return response

def run_answer_appraiser(url,indv_agent, indv_response):
    headers = {'Content-type': 'application/json', 'Accept': 'text/plain'}
    #print(f'sending messages from {indv_agent} to url: {url} at {datetime.datetime.now()}')
    response = requests.post(url=url, headers=headers, json=indv_response, timeout=300)
    return response

def run_utilities(agent, url,indv_agent ,indv_response):

    try:
        if 'nodenorm' in url:

            response = run_node_norm(url,indv_agent, indv_response)
            print(f"Response nodes from {indv_agent} to {url} is : {response.status_code}")
            return response
        elif 'answerappraiser' in url:

            response = run_answer_appraiser(url,indv_agent, indv_response)
            print(f"Response messages from agent {indv_agent} for {url} is : {response.status_code}")
            return response

    except Exception as e:
        print(e)
        return None

def stress_utilities(report, URLS_map, response_list):
    futures=[]
    with ThreadPoolExecutor(max_workers=20) as executor2:
        for agent, url in URLS_map.items():
            report[agent]={}
            report[agent]['status']=[]
            report[agent]['completion_time']=[]
            for response in response_list:
                future = executor2.submit(run_utilities, agent, url,response[0],response[1])
                futures.append([agent,future])
        try:
            for future in futures:
                agent = future[0]
                response = future[1].result()
                if response is not None:
                    report[agent]['status'].append(response.status_code)
                    report[agent]['completion_time'].append(response.elapsed.total_seconds())

        except Exception as e:
            print(e)

        # Wait for all tasks to complete
        executor2.shutdown(wait=True)
    return report

def stress_individual_agents(report, URLS_map, message_list, component, utility_list):
    futures=[]
    with ThreadPoolExecutor(max_workers=30) as executor:
        for agent, url in URLS_map.items():
            report[agent]={}
            report[agent]['status']=[]
            report[agent]['completion_time']=[]
            report[agent]['n_results']=[]
            for mesg in message_list:
                future = executor.submit(send_post_request, url, mesg)
                futures.append([agent,future])
        try:
            for future in futures:
                agent = future[0]
                response = future[1].result()
                if response is not None:
                    if isinstance(response, Exception):
                        n_results=response.text
                    else:
                        content_compress = response.content
                        stringv= content_compress.decode('utf-8')
                        if stringv.startswith('<html>') or '<html' in stringv:
                            soup = BeautifulSoup(stringv, 'html.parser')
                            html_mesg = soup.body.text
                            if html_mesg.startswith('\n'):
                                mesg = html_mesg.replace("\n", "")
                            else:
                                mesg=html_mesg
                            n_results = mesg
                        else:
                            json_data= json.loads(stringv)
                            if 'error' in json_data.keys():
                                n_results = json_data['error']['description']
                            elif 'message' in json_data.keys():
                                if len(json_data['message']) == 0 or json_data['message'] is None or json_data['message']['results'] is None:
                                    n_results = None
                                else:
                                    n_results=len(json_data['message']['results'])

                                if 'Utility' in component and len(json_data['message']) != 0:
                                    #only add the ARA reponses
                                    utility_list.append([agent, json_data])

                    report[agent]['status'].append(response.status_code)
                    report[agent]['completion_time'].append(response.elapsed.total_seconds())
                    report[agent]['n_results'].append(n_results)
                else:
                    report[agent]['status'].append('None')
                    report[agent]['completion_time'].append('None')
                    report[agent]['n_results'].append('None')
        except Exception as e:
            logging.error("Error in getting futures back")
            logging.error("Unexpected error 4: {}".format(traceback.format_exception(type(e), e, e.__traceback__)))
            logging.error(e.__traceback__)

        # Wait for all tasks to complete
        executor.shutdown(wait=True)
    return report, utility_list

async def run_completion(env: str, ARS_URL: str,count: int, predicate:List[str], runner_setting: List[str],biolink_object_aspect_qualifier: List[str],biolink_object_direction_qualifier: List[str],input_category: List[str],input_curie: List[str],component: List[str], output_filename:str):

    if runner_setting == []:
        creative = False
    elif "inferred" in runner_setting:
        creative = True

    message_list = await generate_message(predicate, creative,biolink_object_aspect_qualifier,biolink_object_direction_qualifier,input_category,input_curie)
    report_card={}

    if 'ARAs' in component or 'KPs' in component or 'Utility' in component:
        map = SmartApiDiscover(maturity=x_maturity[env]).ensure()
        utility_list=[]
        if 'ARAs' in component:
            print(f'sending mesg to ARA_url at {datetime.datetime.now()}')
            ARA_URLS_map = await smartapi_registry(map,'ARA')
            report_card, utility_list = stress_individual_agents(report_card, ARA_URLS_map, message_list, component, utility_list)
        if 'KPs' in component:
            print(f'sending mesg to KP_urls at {datetime.datetime.now()}')
            KP_URLS_map = await smartapi_registry(map,'KP')
            message_list_kp = remove_knowledge_type(message_list)
            report_card, utility_list = stress_individual_agents(report_card, KP_URLS_map, message_list_kp, component,utility_list)
        if 'Utility' in component:
            print(f'sending mesg to utility_urls at {datetime.datetime.now()}')
            Utility_URLS_map = await smartapi_registry(map,'Utility')
            utility_scrub_list = scrub_utility_list(utility_list, count)
            report_card = stress_utilities(report_card, Utility_URLS_map, utility_scrub_list)

    if 'ARS' in component:
        report_card['infores:ars']=[]
        ARS_PK_list=[]
        ARS_PK_done=[]
        for idx, mesg in enumerate(message_list):
            if 'error' in mesg.keys():
                report_card['infores:ars'][input_curie[idx]] = mesg
            else:
                pk = await call_ars(mesg, ARS_URL)
                ARS_PK_list.append((pk,input_curie[idx]))

        print(f'the following pks are going to be is: {ARS_PK_list}')
        start_time=time.time()
        print('starting......')
        while (time.time()-start_time)/60<30:
            for item in ARS_PK_list:
                parent_pk=item[0]
                url = ARS_URL + "messages/" + parent_pk + "?trace=y"
                async with httpx.AsyncClient(verify=False) as client:
                    r = await client.get(url, timeout=60)
                try:
                    rj = r.json()
                except json.decoder.JSONDecodeError:
                    print("Non-JSON content received:")
                    print(r.text)
                if rj["status"]=="Done":
                    if item not in ARS_PK_done:
                        print(f'{item[1]} : {item[0]} added to the Done list')
                        ARS_PK_done.append(item)
                    else:
                        pass
                elif rj["status"]=='Running' or rj["status"]=='Error':
                    pass
            if len(ARS_PK_done) == len(ARS_PK_list):
                time.sleep(90)
                break
        else:
            for item in ARS_PK_list:
                parent_pk=item[0]
                url = ARS_URL + "messages/" + parent_pk + "?trace=y"
                async with httpx.AsyncClient(verify=False) as client:
                    r = await client.get(url,timeout=60)
                rj = r.json()
                if rj["status"]=="Running":
                    print(f'the following pk is still running after 30 min  in {parent_pk}')
                    ARS_PK_done.append(item)
                else:
                    pass
        for item in ARS_PK_done:
            pk=item[0]
            file = item[1]
            url = ARS_URL + "messages/" + pk + "?trace=y"
            async with httpx.AsyncClient(verify=False) as client:
                r = await client.get(url,timeout=60)
            try:
                rj = r.json()
            except json.decoder.JSONDecodeError:
                print("Non-JSON content received:")
                print(r.text)
            query_report =await get_children_info(rj,pk,file,ARS_URL)
            if query_report is not None:
                merged_report = await get_merged_info(rj, ARS_URL)
                query_report[file]['merge_report'] = merged_report
            key=file
            if report_card['infores:ars'] != []:
                rep = {k: v for d in report_card['infores:ars'] for k, v in d.items()}
                repeat_count=sum([1 for key in rep.keys() if key.startswith(f"{file}")])
                if repeat_count >= 1:
                    query_report[f'{key}_run_{repeat_count+1}']=query_report[key]
                    del query_report[key]
                    report_card['infores:ars'].append(query_report)
                else:
                    if input_curie.count(key) > 1:
                        query_report[f'{key}_run_1']=query_report[key]
                        del query_report[key]
                        report_card['infores:ars'].append(query_report)
                    else:
                        report_card['infores:ars'].append(query_report)
            else:
                if input_curie.count(key) > 1:
                    query_report[f'{key}_run_1']=query_report[key]
                    del query_report[key]
                    report_card['infores:ars'].append(query_report)
                else:
                    report_card['infores:ars'].append(query_report)

        complete_queries = await add_total_completion_time(report_card['infores:ars'])

    # with open(output_filename, "w") as f:
    #     json.dump(report_card, f, indent=4)

    return report_card


async def run_load_testing(env: str, count: int, predicate: List[str],runner_setting: List[str],biolink_object_aspect_qualifier: List[str],biolink_object_direction_qualifier: List[str],input_category: List[str],input_curie: List[str],component:List[str]):

    ars_env = env_spec[env]
    ARS_URL = f'https://{ars_env}.transltr.io/ars/api/'
    timestamp = datetime.datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
    output_filename = f"ARS_smoke_test_{timestamp}.json"

    if count > len(predicate):
        for input_arg in [predicate,biolink_object_aspect_qualifier,biolink_object_direction_qualifier,input_category,input_curie]:
            while count > len(input_arg):
                diff = count - len(input_arg)
                input_arg.extend(input_arg[0:diff])

    report_card = await run_completion(env, ARS_URL, count, predicate, runner_setting, biolink_object_aspect_qualifier,
                                       biolink_object_direction_qualifier, input_category, input_curie, component,
                                       output_filename)

    return report_card, ARS_URL


if __name__ == "__main__":

    args = parser.parse_args()
    env = getattr(args, "env")
    count = getattr(args,"count")
    predicate = getattr(args, "predicate")
    runner_setting = getattr(args, "runner_setting")
    biolink_object_aspect_qualifier = getattr(args, "biolink_object_aspect_qualifier")
    biolink_object_direction_qualifier = getattr(args, "biolink_object_direction_qualifier")
    input_category = getattr(args,"input_category")
    input_curie = getattr(args, "input_curie")
    component = getattr(args,"component")

    current_time = datetime.datetime.now()
    formatted_start_time = current_time.strftime('%H:%M:%S')

    print(f"started performing ARS_Load_Testing at {formatted_start_time}")
    print(asyncio.run(run_load_testing(env,count, predicate,runner_setting,biolink_object_aspect_qualifier,biolink_object_direction_qualifier,input_category,input_curie,component)))
    endtime = datetime.datetime.now()
    formatted_end_time = endtime.strftime('%H:%M:%S')
    print(f"finished running Load Testing at {formatted_end_time}")