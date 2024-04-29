# -*- coding: utf-8 -*-

import click
import ast
import asyncio
import datetime
from PerformanceTestRunner.load_test import run_load_testing
from pkg_resources import get_distribution, DistributionNotFound
from warnings import simplefilter
# ignore all future warnings
simplefilter(action='ignore', category=FutureWarning)

try:
    __version__ = get_distribution("PerformanceTestRunner").version
except DistributionNotFound:
    # package is not installed
    pass

class PythonLiteralOption(click.Option):

    def type_cast_value(self, ctx, value):
        try:
            return ast.literal_eval(value)
        except:
            raise click.BadParameter(value)

@click.command(context_settings=dict(help_option_names=['-h', '--help']))
@click.version_option(version=__version__)
@click.option('--env', type=click.Choice(['dev', 'ci', 'test', 'prod'], case_sensitive=False))
@click.option('--count', type=click.INT, help='number of concurrent queries to send')
@click.option('--predicate', cls=PythonLiteralOption,type=click.Choice(['treats','affects']))
@click.option('--runner_setting', cls=PythonLiteralOption, help='creative mode indicator(inferred)')
@click.option('--biolink_object_aspect_qualifier', cls=PythonLiteralOption, help='aspect qualifier')
@click.option('--biolink_object_direction_qualifier', cls=PythonLiteralOption, help='direction qualifier')
@click.option('--input_category', cls=PythonLiteralOption, help='Input Type Category List')
@click.option('--input_curie', cls=PythonLiteralOption, help='Input Curie List')
@click.option('--component', cls=PythonLiteralOption, help='Services to run the stress test on[ARA,ARAs,KPs,Utility]')

def main(env,count, predicate, runner_setting, biolink_object_aspect_qualifier, biolink_object_direction_qualifier, input_category, input_curie,component):

    current_time = datetime.datetime.now()
    formatted_time = current_time.strftime('%H:%M:%S')

    click.echo(f"started performing Single Level ARS_Test Analysis at {formatted_time}")
    click.echo(asyncio.run(run_load_testing(env,count, predicate,runner_setting,biolink_object_aspect_qualifier,biolink_object_direction_qualifier,input_category,input_curie,component)))
    endtime = datetime.datetime.now()
    click.echo(f"finished running the pipeline at {endtime}")

