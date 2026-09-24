import React,{useState} from 'react';
import {Linking,Platform,View} from 'react-native';
import Constants from 'expo-constants';
import Text from './AppText';
import {Button,Card,Note,S} from './theme';
import {Disclosure} from './DesignPrimitives';

export function AccountSettings({notifications=false,onInbox}:{notifications?:boolean;onInbox():void}){
 const [error,setError]=useState('');
 return <><Card><Text style={S.heading}>{notifications?'알림 확인':'앱 권한'}</Text><Note>{notifications?'미션과 보상 소식은 앱의 알림함에서 확인할 수 있습니다.':'위치 접근 권한과 사진 접근 권한은 휴대폰 설정에서 관리할 수 있습니다.'}</Note>{notifications?<Button title="알림함 보기" onPress={onInbox}/>:<Button title="휴대폰 설정 열기" onPress={()=>{if(Platform.OS==='web'){setError('iPhone 앱에서 사용할 수 있습니다.');return;}void Linking.openSettings().catch(()=>setError('휴대폰 설정 앱에서 Canopy를 선택해주세요.'));}}/>}{!!error&&<Note>{error}</Note>}</Card>{!notifications&&<Card><Text style={S.label}>앱 버전</Text><Text style={S.note}>{Constants.expoConfig?.version??'확인 중'}</Text><Text style={S.label}>화면 움직임</Text><Note>휴대폰의 동작 줄이기 설정을 따릅니다.</Note></Card>}</>;
}
export function UserGuide(){return <>{[
 ['이동 시작하기','홈에서 나의 이동 시작하기를 누르세요. 현재 위치를 확인한 다음 목적지를 선택하면 경로와 보상 기준이 표시됩니다. 목적지 없이도 여정을 기록할 수 있습니다.'],
 ['이동 기록하기','여정 중에는 이동 시간과 거리, 속도를 확인할 수 있습니다. 이동 정보는 접거나 다시 펼칠 수 있습니다. 기록을 마치려면 여정 종료를 누르세요.'],
 ['백그라운드 위치','이동 기록에 필요한 위치 권한을 허용해주세요. 휴대폰 설정과 위치 신호 상태에 따라 기록이 제한될 수 있습니다. 앱을 강제로 종료하면 기록이 중단될 수 있습니다.'],
 ['보상 받기','여정의 최종 탄소 배출량을 비교 기준과 비교해 보상을 계산합니다. 절감량이 작거나 위치 기록이 부족하면 지급되지 않을 수 있습니다.'],
 ['미션 달성하기','여정을 기록하면 해당 미션의 진행 상황이 자동으로 갱신됩니다. 목표를 달성한 미션에서 보상 받기를 누르세요.'],
 ['리워드 교환','지갑의 상품 목록은 교환 화면 미리보기입니다. 아직 실제 상품 교환이나 토큰 차감은 지원하지 않습니다.']
 ].map(([title,body])=><Card key={title}><Text style={S.heading}>{title}</Text><Note>{body}</Note></Card>)}</>;}

// Operator details and retention/deletion policy must be confirmed before publication.
export function PrivacyNotice(){return <><Text style={S.note}>서비스 검토용 초안</Text><Text style={S.heading}>Canopy 개인정보처리방침</Text><Note>Canopy는 이동 기록을 분석해 탄소 배출량과 보상을 제공하는 서비스입니다. 아래 내용은 현재 구현된 데이터 처리 방식을 기준으로 작성했습니다.</Note>{[
 ['1. 처리하는 개인정보','계정 생성 시 이메일, 닉네임, 비밀번호 검증 정보와 캠페인 참여정보를 처리합니다. 사용자가 등록하면 프로필 사진, 부서, 집과 직장 위치도 저장합니다. 비밀번호 원문은 저장하지 않습니다.'],
 ['2. 위치정보와 이용 기록','여정 기록 시 위치 좌표, 측정 시각, 위치 정확도, 속도, 기기 식별정보와 여정 식별정보를 처리합니다. 이동수단 분석 결과, 거리, 탄소 배출량, 보상 내역, 미션 진행 상황과 제출한 피드백을 저장합니다.'],
 ['3. 이용 목적','회원 확인, 여정 기록, 이동수단 분석, 탄소 배출량 산정, 보상 지급, 중복 지급 방지, 미션과 랭킹 제공, 오류 확인에 사용합니다. 목적지 검색과 경로 안내를 위해 입력한 장소 및 출발 좌표와 목적지 좌표를 경로 서비스에 전달합니다.'],
 ['4. 공개되는 정보','같은 캠페인의 랭킹에는 닉네임과 프로필 사진, 순위 및 집계 점수가 표시됩니다. 프로필 사진은 내 정보에서 변경하거나 삭제할 수 있습니다.'],
 ['5. 저장 및 외부 서비스','이동 및 계정 데이터는 Microsoft Azure 기반 서버에서 처리합니다. 이동 분석에는 Azure Databricks를 사용합니다. 경로 안내에는 TMAP 서비스를 사용합니다. 구체적인 수탁자, 처리 지역 및 국외 이전 해당 여부는 운영 계약 확인 후 확정할 예정입니다.'],
 ['6. 보유기간과 파기','계정, 위치 원본, 분석 결과와 보상 기록의 보유기간 및 파기 절차는 정식 운영 정책 확정 후 게시할 예정입니다. 현재 앱에는 계정 및 이동 기록을 직접 삭제하는 기능이 제공되지 않습니다.'],
 ['7. 이용자의 선택','프로필 정보는 내 정보에서 수정할 수 있습니다. 위치 및 사진 접근 권한은 휴대폰 설정에서 변경할 수 있습니다. 위치 권한을 해제하면 여정 기록 기능의 이용이 제한됩니다. 열람, 정정, 삭제 및 처리정지 요청을 위한 접수 창구는 아래 운영 연락처 확정 후 안내합니다.'],
 ['8. 운영 및 문의','운영 주체: 등록 예정\n개인정보 보호 담당자: 등록 예정\n문의 이메일: 등록 예정'],
 ['9. 시행과 변경','시행일은 정식 운영 정책 확정 후 안내합니다. 운영 주체와 문의 창구, 보유기간 및 외부 처리 계약이 확인되기 전까지 본 문서는 검토용 초안입니다.']
 ].map(([title,body])=><Card key={title}><Text style={[S.heading,{fontSize:16}]}>{title}</Text><Text style={S.note}>{body}</Text></Card>)}</>;}
