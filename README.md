
Performance Testing 
==========================================================

This testing framework performs stress/load testing on ARS, ARAs, KPs, sri-node-normalizer and 
sri-answer-appraiser services 

### Performance Test Runner Implementation
```bash
pip install PerformanceTestRunner 
```

### CLI
The command-line interface is the easiest way to run the PerformanceTestRunner
After installation, simply type PerformanceTestRunner --help to see required input arguments & options
- `PerformanceTestRunner`
    - env : the environment to run the queries against (dev|ci|test|prod)
    - count: number of concurrent queries to run
    - predicate: treats|affects
    - runner_setting: creative mode inidicator (inferred)
    - biolink_object_aspect_qualifier: activity_or_abundance
    - biolink_object_direction_qualifier: increased/decreased
    - input_category: input type category (Gene/ChemicalEntity)
    - input_curie: normalized curie taken from assest.csv
    - component: service to stress (ARS|ARAs|KPs|Utility)

- example:
  - PerformanceTestRunner --env 'ci' --count 5 --predicate '["treats", "affects","affect","treats", "affects"]' --runner_setting '["inferred"]' --biolink_object_aspect_qualifier '["","activity_or_abundance","activity_or_abundance","","activity_or_abundance"]' --biolink_object_direction_qualifier '["","increased","decreased","","increased"]' --input_category '["biolink:Disease","biolink:Gene","biolink:ChemicalEntity","biolink:Disease","biolink:Gene"]' --input_curie '["MONDO:0009265","NCBIGene:23394","PUBCHEM.COMPOUND:5881","MONDO:0015564","NCBIGene:4318"]' --component '["ARS","ARAs", "KPs", "Utility"]'



### python
``` python 
import asyncio
from PerformanceTestRunner.load_test import run_load_testing
asyncio.run(run_load_testing('ci',3, ['treats','affects','affects'],['inferred'],['','activity_or_abundance','activity_or_abundance'],['','increased','decreased'],['biolink:Disease','biolink:Gene','biolink:ChemicalEntity'],['MONDO:0009265','NCBIGene:23394','PUBCHEM.COMPOUND:5881'],['ARS','ARAs', 'KPs', 'Utility']))
```
OR
``` python 
python load_test.py --env 'ci' --count 3 --predicate 'treats' 'affects' 'affects' --runner_setting 'inferred'  --biolink_object_aspect_qualifier '' 'activity_or_abundance' 'activity_or_abundance' --biolink_object_direction_qualifier '' 'increased' 'decreased'  --input_category 'biolink:Disease' 'biolink:Gene' 'biolink:ChemicalEntity' --input_curie 'MONDO:0009265' 'NCBIGene:23394' 'PUBCHEM.COMPOUND:5881' --component 'ARS' 'ARAs' 'KPs' 'Utility'
```






