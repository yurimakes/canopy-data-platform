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


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('--inputs', type=Path, default=DATA/'inputs')
    parser.add_argument('--output', type=Path, default=DATA/'weekly')
    parser.add_argument('--state', type=Path)
    parser.add_argument('--runtime',choices=('local','databricks'),default='local')
    parser.add_argument('--exported-ledger',action='store_true',help='Use validated paid Trip ledger from the input snapshot')
    parser.add_argument('--conversion-rate',type=float,default=1.0)
    parser.add_argument('--commute-verified', action='store_true',help='Isolated fixture scope verified by the operator')
    parser.add_argument('--include-mock',action='store_true',help='Only for isolated fixture output/state')
    args=parser.parse_args(argv)
    args.inputs=args.inputs.resolve()
    args.output=args.output.resolve()
    if args.state:args.state=args.state.resolve()
    if args.include_mock and (not args.state or args.state==DATA or args.output==DATA/'weekly'):
        raise ValueError('Mock scenarios require isolated --state and --output')
    # Databricks Connect 설정이 있는 PC에서도 반드시 로컬 Spark로 실행
    if args.runtime=='local':
        for key in ('SPARK_REMOTE','DATABRICKS_HOST','DATABRICKS_TOKEN','SPARK_CONNECT_MODE_ENABLED'):os.environ.pop(key,None)
        os.environ['SPARK_LOCAL_IP']='127.0.0.1'
        os.environ['PYSPARK_PYTHON']=sys.executable
        os.environ['PYTHONPATH']=os.pathsep.join([str(TEAM.parent/'databricks'),str(TEAM),str(ROOT)])
    from pyspark.sql import SparkSession, functions as F, types as T
    spark=(SparkSession.builder.master('local[2]').appName('Canopy local weekly')
        .config('spark.driver.memory','2g')
        .config('spark.ui.enabled','false').config('spark.sql.shuffle.partitions','2')
        .config('spark.sql.session.timeZone','UTC').config('spark.sql.execution.arrow.pyspark.enabled','true')
        .config('spark.driver.bindAddress','127.0.0.1').config('spark.driver.host','127.0.0.1').getOrCreate()) if args.runtime=='local' else SparkSession.builder.getOrCreate()
    if args.runtime=='local':spark.sparkContext.setLogLevel('ERROR')
    if args.runtime=='local':spark.conf.set('CANOPY_BASELINE_WEEKLY_COMMUTE_VERIFIED',str(args.commute_verified).lower())
    spark.conf.set('spark.sql.session.timeZone','UTC')
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
    # Serverless uses Spark Connect's reader, not the classic JVM reader class.
    reader_type=type(spark.read)
    old_table=reader_type.table
    reader_type.table=lambda self,name:old_table(self,name.split('.')[-1])
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
    if args.include_mock:
        trips=[{**t,'is_mock':False,'confirmed_trip':{**(t.get('confirmed_trip') or {}),'is_mock':False},'commute_verified':args.commute_verified or t.get('commute_verified',False)} for t in trips]
    module.COMMUTE_SCOPE_VERIFIED=True
    # 실제 저장 계약의 동일 필드만 사용. 탄소값과 거리는 재생성하지 않음
    for t in trips:
        t['document_json']=json.dumps(t,default=str)
    frame(trips,module.FINAL_TRIP_SCHEMA).createOrReplaceTempView('final_trips')
    out=args.output.resolve()
    out.mkdir(parents=True,exist_ok=True)
    report={'environment':args.runtime,'azure_used':args.runtime=='databricks','input_trips':len(trips),'stages':{}}
    if not any(t.get('status')=='ready' for t in trips):
        report['stages']={name:{'status':'waiting_for_input'} for name in registry}
        (out/'last-attempt.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print('완료된 Final Trip 입력 없음. ML 처리 완료 후 다시 실행해주세요.',flush=True)
        reader_type.table=old_table
        if args.runtime=='local':spark.stop()
        raise SystemExit(2)
    from build_mission_profile import build_profile_from_weekly_summary,_gold_profile,_responses_to_bundles
    from business import mission_history,issue,weekly_outputs
    from reward_baselines import paid_trip_history,publish_completed_weeks
    from reward_ledger import LEDGER_HISTORY_SCHEMA
    state=args.state.resolve() if args.state else (DATA if out==DATA/'weekly' else out/'state')
    results={}
    report['conversion_rate']=args.conversion_rate
    report['development_only']=args.runtime=='local'
    report['reward_mode']='trip-ledger-only'
    from weekly_ledger import validate_paid_ledger
    def ledger_rows():return validate_paid_ledger(read_json('reward_ledger_history') if args.exported_ledger else paid_trip_history(state))
    materialized_inputs['reward_ledger_history']=ledger_rows()
    def write(name,rows):
        results[name]=rows
        report['stages'][name]={'status':'passed','rows':len(rows)}
        print(name,len(rows),flush=True)
        return rows
    def save(name,df):
        rows=[r.asDict(recursive=True) for r in df.collect()]
        if name=='ranking':
            from business import read_rows
            from weekly_ledger import finalize_rankings
            from reward_baselines import week_of
            previous=read_json('previous_ranking') if args.exported_ledger else read_rows(out/'ranking.json')
            rows=finalize_rankings(previous,rows,week_of())
        frame(rows,df.schema).createOrReplaceTempView(name)
        return write(name,rows)
    stages=['final_trip_gold_input','weekly_summary','weekly_gold','baseline_eligibility','personal_baseline',
        'personal_ready_users','global_eligibility','global_baseline','baseline_gold','behavior_change',
        'mission_response_weekly','weekly_user_profile','next_week_missions','reward_calculation','reward_ledger',
        'ranking','campaign_kpi','weekly_outputs_gold']
    try:
        for name in stages:
            if name=='baseline_eligibility':
                spark.read.table('commute_weekly_gold').createOrReplaceTempView('weekly_gold')
            if name=='behavior_change':
                frame(results['weekly_gold'],module.WEEKLY_SCHEMA).createOrReplaceTempView('weekly_gold')
            if name=='mission_response_weekly':
                _,progress,responses=mission_history(state,trips,read_json('mission_bundles'),read_json('mission_events') if args.exported_ledger else None)
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
                bundles=[issue(state,p,datetime.fromisoformat(p['effective_week_start']).date(),[p],persist=False) for p in results['weekly_user_profile']]
                df=frame(bundles,module.MISSION_BUNDLE_SCHEMA)
            elif name=='reward_ledger':
                ledger=ledger_rows()
                materialized_inputs['reward_ledger_history']=ledger
                write(name,ledger);continue
            elif name=='weekly_outputs_gold':
                df=frame(weekly_outputs(results),module.WEEKLY_OUTPUTS_DRAFT_SCHEMA)
            else:df=registry[name]()
            save(name,df)
            if name=='weekly_gold':
                verified_rows=[r for r in results['final_trip_gold_input'] if json.loads(r.get('document_json') or '{}').get('commute_verified') is True]
                if len(verified_rows)==len(results['final_trip_gold_input']):
                    commute_weekly=save('commute_weekly_gold',frame(results['weekly_gold'],module.WEEKLY_SCHEMA))
                else:
                    # Do not duplicate the full raw document in Spark's aggregation plan.
                    compact=[{k:v for k,v in r.items() if k!='document_json'} for r in verified_rows]
                    commute_weekly=save('commute_weekly_gold',module.calculate_weekly(frame(compact,module.FINAL_TRIP_SCHEMA)))
        results['effective_personal_baseline']=publish_completed_weeks(state,commute_weekly,users,True,persist=False)
    except Exception as exc:
        report['stages'][name]={'status':'failed','error':str(exc)}
        for pending in stages[stages.index(name)+1:]:report['stages'][pending]={'status':'blocked','dependency':name}
        raise
    finally:
        succeeded=all(s.get('status')=='passed' for s in report['stages'].values())
        report['completed_at']=datetime.now().astimezone().isoformat()
        try:
            if succeeded:
                from weekly_publication import publish
                try:publish(out,results,report)
                except Exception:
                    report['stages']['publication']={'status':'failed','error':'atomic publication failed'}
                    (out/'last-attempt.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
                    raise
            else:
                path=out/'last-attempt.json'
                temp=path.with_suffix('.tmp');temp.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(path)
        finally:
            reader_type.table=old_table
            spark.createDataFrame=original_create
            if args.runtime=='local':spark.stop()


if __name__=='__main__':main()
