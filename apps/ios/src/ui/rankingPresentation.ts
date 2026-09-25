import type {RankingView} from './CommunityPanels';

const names=['신민철','김창연','박준용','김이레','최유리','양유진','이지우','정하윤','박서준','김도윤','한서연','윤지호','오수빈','이예은','정유나','김지민','송현우','임수아','강민준','장서윤','이준서','김채원','정수현','조하늘','박지안','윤서우','권도현','한지유','임서진','송민재'];
function displayName(index:number){
 if(index<names.length)return names[index];
 const i=index-names.length;
 return ['김','이','박','최','정','강','조','윤','장','임'][Math.floor(i/17)%10]+['서아','하준','지안','도현','서윤','유준','하린','시우','지유','지호','수아','준우','지민','소율','예준','다은','채윤'][i%17];
}
// Presentation only: seeded test campaigns use the approved demo roster.
// Never write these names, points or positions back to accounts/rewards.
export function rankingPresentation(input:RankingView['personal'],personal:boolean){
 const demo=personal&&input.some(row=>/^테스트\s*직원/.test(row.name));
 const rows=[...input].sort((a,b)=>a.rank-b.rank||a.id.localeCompare(b.id));
 if(demo){
  const owner=rows.findIndex(row=>row.name==='신민철'||row.name==='민철');
  if(owner>0)rows.unshift(...rows.splice(owner,1));
 }
 return rows.map((row,index)=>({...row,rank:index+1,...(demo?{name:displayName(index),points:(rows.length-index)*7+180,avatarDataUri:null}: {})}));
}
