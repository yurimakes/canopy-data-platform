"""팀 Weekly 변환을 로컬 Spark에서 실행. Lakeflow 실행·Azure 저장은 제외."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys
import types
from datetime import datetime, timedelta

ROOT=Path(__file__).resolve().parents[2]
DATA=ROOT/'.local-data'
TEAM=ROOT/'cloud/azure/pipelines/weekly_analysis'


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--inputs', type=Path, default=DATA/'inputs')
    parser.add_argument('--output', type=Path, default=DATA/'weekly')
    parser.add_argument('--state', type=Path)
    parser.add_argument('--conversion-rate',type=float,default=1.0)
    parser.add_argument('--commute-verified', action='store_true')
    args=parser.parse_args()
    args.inputs=args.inputs.resolve()
    args.output=args.output.resolve()
    # Databricks Connect 설정이 있는 PC에서도 반드시 로컬 Spark로 실행
    for key in ('SPARK_REMOTE','DATABRICKS_HOST','DATABRICKS_TOKEN','SPARK_CONNECT_MODE_ENABLED'):
        os.environ.pop(key,None)
    os.environ['SPARK_LOCAL_IP']='127.0.0.1'
    os.environ['PYSPARK_PYTHON']=sys.executable
    os.environ['PYTHONPATH']=os.pathsep.join([str(TEAM.parent/'databricks'),str(TEAM),str(ROOT)])
    from pyspark.sql import SparkSession, functions as F, types as T
    from pyspark.sql.readwriter import DataFrameReader
    spark=(SparkSession.builder.master('local[2]').appName('Canopy local weekly')
        .config('spark.ui.enabled','false').config('spark.sql.shuffle.partitions','2')
        .config('spark.sql.session.timeZone','UTC').config('spark.sql.execution.arrow.pyspark.enabled','true')
        .config('spark.driver.bindAddress','127.0.0.1').config('spark.driver.host','127.0.0.1').getOrCreate())
    spark.sparkContext.setLogLevel('ERROR')
    spark.conf.set('CANOPY_BASELINE_WEEKLY_COMMUTE_VERIFIED',str(args.commute_verified).lower())
    registry={}
    dp=types.ModuleType('pyspark.pipelines')
    def decorator(**options):
        def register(fn):
            registry[options.get('name',fn.__name__)]=fn
            return fn
        return register
    dp.temporary_view=dp.materialized_view=decorator
    sys.modules['pyspark.pipelines']=dp
    import pyspark
    pyspark.pipelines=dp
    old_table=DataFrameReader.table
    DataFrameReader.table=lambda self,name:old_table(self,name.split('.')[-1])
    os.chdir(TEAM)
    sys.path[:0]=[str(TEAM),str(TEAM.parent/'databricks')]
    spec=importlib.util.spec_from_file_location('local_weekly_team',TEAM/'weekly_pipeline.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    def frame(rows,schema):
        # JSON 파싱으로 timestamp/중첩 컬럼까지 팀 DDL 그대로 적용
        raw=spark.range(len(rows)).select(F.col('id').cast('int').alias('index'))
        if not rows:return spark.range(0).select(F.from_json(F.lit('{}'),schema).alias('row')).select('row.*')
        encoded=[json.dumps(row,default=str) for row in rows]
        values=F.array(*[F.lit(value) for value in encoded])
        return raw.select(F.from_json(F.element_at(values,F.col('index')+1),schema).alias('row')).select('row.*')
    original_create=spark.createDataFrame
    def local_create(data,schema=None,*args,**kwargs):
        if isinstance(data,list) and not data and schema is not None:
            return frame([],schema)
        return original_create(data,schema,*args,**kwargs)
    spark.createDataFrame=local_create
    def read_json(name):
        path=args.inputs/(name+'.json')
        return json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else []
    materialized_inputs={}
    users=read_json('users')
    membership=[{'user_id':u['user_id'],'campaign_id':u['campaign_id'],'department_id':u.get('department_id'),
        'joined_at':u.get('campaign_joined_at'),'left_at':u.get('campaign_left_at')} for u in users]
    def optional(path,schema,input_name):
        rows=membership if input_name=='campaign_membership_raw' else materialized_inputs.get(input_name,read_json(input_name))
        if input_name=='mission_profile':return spark.read.table('local_mission_profile')
        return frame(rows,schema)
    module._read_optional_delta=optional
    module.REWARD_CONVERSION_RATE_OVERRIDE=args.conversion_rate
    trips=read_json('trips')
    # 실제 저장 계약의 동일 필드만 사용. 탄소값과 거리는 재생성하지 않음
    for t in trips:
        t['document_json']=json.dumps(t,default=str)
    frame(trips,module.FINAL_TRIP_SCHEMA).createOrReplaceTempView('final_trips')
    out=args.output.resolve()
    out.mkdir(parents=True,exist_ok=True)
    for old in out.glob('*.json'):
        if old.stem in registry or old.name=='run.json':old.unlink()
    report={'environment':'local','azure_used':False,'input_trips':len(trips),'stages':{}}
    if not any(t.get('status')=='ready' for t in trips):
        report['stages']={name:{'status':'waiting_for_input'} for name in registry}
        (out/'run.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print('완료된 Final Trip 입력 없음. ML 처리 완료 후 다시 실행해주세요.',flush=True)
        spark.stop()
        raise SystemExit(2)
    from build_mission_profile import build_profile_from_weekly_summary,_gold_profile,_responses_to_bundles
    from business import mission_history,issue,publish_rewards,weekly_outputs
    from reward_ledger import LEDGER_HISTORY_SCHEMA
    state=args.state.resolve() if args.state else (DATA if out==DATA/'weekly' else out/'state')
    results={}
    report['conversion_rate']=args.conversion_rate
    report['development_only']=True
    def write(name,rows):
        results[name]=rows
        path=out/(name+'.json')
        temp=path.with_suffix('.tmp');temp.write_text(json.dumps(rows,default=str,ensure_ascii=False),encoding='utf-8');temp.replace(path)
        report['stages'][name]={'status':'passed','rows':len(rows)}
        print(name,len(rows),flush=True)
        return rows
    def save(name,df):
        rows=[r.asDict(recursive=True) for r in df.collect()]
        frame(rows,df.schema).createOrReplaceTempView(name)
        return write(name,rows)
    stages=['final_trip_gold_input','weekly_summary','weekly_gold','baseline_eligibility','personal_baseline',
        'personal_ready_users','global_eligibility','global_baseline','baseline_gold','behavior_change',
        'mission_response_weekly','weekly_user_profile','next_week_missions','reward_calculation','reward_ledger',
        'ranking','campaign_kpi','weekly_outputs_gold']
    try:
        for name in stages:
            if name=='mission_response_weekly':
                _,progress,responses=mission_history(state,trips,read_json('mission_bundles'))
                write('mission_progress',progress)
                write(name,responses);materialized_inputs[name]=responses
                continue
            if name=='weekly_user_profile':
                profiles=[]
                for row in results['weekly_gold']:
                    start=datetime.strptime(row['week']+'-1','%G-W%V-%u').date()
                    history=[r for r in results['mission_response_weekly'] if r['user_id']==row['user_id'] and r['campaign_id']==row['campaign_id'] and r['week_start']<=str(start)]
                    profiles.append(_gold_profile(build_profile_from_weekly_summary(row,user_id=row['user_id'],campaign_id=row['campaign_id'],source_week_start=str(start),source_week_end=str(start+timedelta(days=7)),bundle_history=_responses_to_bundles(history),mission_history_source='local_mission_response')))
                frame(profiles,module.PROFILE_SCHEMA).createOrReplaceTempView('local_mission_profile')
            if name=='next_week_missions':
                bundles=[issue(state,p,datetime.fromisoformat(p['effective_week_start']).date(),[p]) for p in results['weekly_user_profile']]
                df=frame(bundles,module.MISSION_BUNDLE_SCHEMA)
            elif name=='reward_ledger':
                ledger=publish_rewards(state,results['reward_calculation'])
                materialized_inputs['reward_ledger_history']=ledger
                save(name,frame(ledger,LEDGER_HISTORY_SCHEMA));continue
            elif name=='weekly_outputs_gold':
                df=frame(weekly_outputs(results),module.WEEKLY_OUTPUTS_DRAFT_SCHEMA)
            else:df=registry[name]()
            save(name,df)
    except Exception as exc:
        report['stages'][name]={'status':'failed','error':str(exc)}
        for pending in stages[stages.index(name)+1:]:report['stages'][pending]={'status':'blocked','dependency':name}
        raise
    finally:
        (out/'run.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        spark.stop()


if __name__=='__main__':main()
