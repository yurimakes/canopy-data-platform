from setuptools import setup, find_namespace_packages

setup(
    name='canopy-downstream-5dt024', version='0.3.9',
    py_modules=['downstream_bootstrap', 'downstream_tasks', 'downstream_qa'],
    packages=['canopy_runtime']+['canopy_runtime.'+p for p in find_namespace_packages('runtime')]+['final_trip','weekly_etl'],
    package_dir={'canopy_runtime':'runtime','final_trip':'../final-trip/final_trip','weekly_etl':'../weekly/weekly_etl'},
    package_data={'': ['*.yaml','*.yml','*.json']},
    python_requires='>=3.11',
)
