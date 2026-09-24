export function locationError(error:unknown):string {
  if(error&&typeof error==='object'&&'code' in error){
    if(error.code===1)return '위치 권한이 꺼져 있어요. 브라우저 또는 기기 설정에서 위치 접근을 허용해주세요.';
    if(error.code===2)return '현재 위치를 찾지 못했어요. 위치 서비스를 켜고 수신이 잘 되는 곳에서 다시 시작해주세요.';
    if(error.code===3)return '위치를 기다리는 시간이 길어졌어요. 위치 서비스를 확인하고 다시 시작해주세요.';
  }
  return error instanceof Error?error.message:'위치 기록을 시작하지 못했어요. 잠시 후 다시 시도해주세요.';
}
