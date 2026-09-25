import React from 'react';
import {act,create,type ReactTestRenderer} from 'react-test-renderer';
import {afterEach,expect,it,vi} from 'vitest';
import {JourneyInfoPanel} from './JourneyInfoPanel';
import {ServiceScreen,type ServiceProps} from './ServiceScreen';

const windowSize=vi.hoisted(()=>({width:375,height:667,scale:1,fontScale:1}));
vi.mock('react-native',()=>({View:'View',Pressable:'Pressable',ScrollView:'ScrollView',Image:'Image',ImageBackground:'ImageBackground',Modal:'Modal',ActivityIndicator:'ActivityIndicator',useWindowDimensions:()=>windowSize}));
vi.mock('react-native-safe-area-context',()=>({SafeAreaView:'SafeAreaView',SafeAreaProvider:'SafeAreaProvider'}));
vi.mock('expo-constants',()=>({default:{expoConfig:{extra:{localOnly:false}}}}));
vi.mock('../communityClient',()=>({localAction:vi.fn(async()=>({}))}));
vi.mock('./RewardShop',()=>({RewardShop:'RewardShop'}));
vi.mock('./AccountPages',()=>({AccountSettings:'AccountSettings',PrivacyNotice:'PrivacyNotice',UserGuide:'UserGuide'}));
vi.mock('./IllustratedIcon',()=>({IllustratedIcon:'IllustratedIcon'}));
vi.mock('./ProfileAvatar',()=>({ProfileAvatar:'ProfileAvatar',chooseProfilePhoto:vi.fn()}));
vi.mock('./DesignPrimitives',()=>({Eyebrow:'Eyebrow'}));
vi.mock('./AppText',()=>({default:'Text'}));
vi.mock('./theme',()=>({C:{},S:{},Note:'Note',Icon:'Icon',Button:'Button',Card:'Card',Fade:'Fade',Field:'Field',Stat:'Stat'}));
vi.mock('./ActiveJourney',()=>({ActiveJourney:'ActiveJourney'}));
vi.mock('./NotificationPanel',()=>({NotificationPanel:'NotificationPanel'}));
vi.mock('./JourneyHistory',()=>({JourneyHistory:'JourneyHistory'}));
vi.mock('./HomeDashboard',()=>({HomeDashboard:'HomeDashboard'}));
vi.mock('./RewardExperience',()=>({JourneyComplete:'JourneyComplete'}));
vi.mock('./MascotMedia',()=>({ProcessingStatus:'ProcessingStatus',MascotMedia:'MascotMedia',MapFace:'MapFace'}));
vi.mock('./CanopyMascot',()=>({CanopyMascot:'CanopyMascot'}));
vi.mock('./LocalTools',()=>({LivePrediction:'LivePrediction',LocalWeekly:'LocalWeekly'}));
vi.mock('./MeasurementScreen',()=>({MeasurementScreen:'MeasurementScreen'}));
vi.mock('./TripResult',()=>({TripResult:'TripResult'}));
vi.mock('./RoutePlanner',()=>({PlacePicker:'PlacePicker',RoutePlanner:'RoutePlanner',RouteStrip:'RouteStrip'}));
vi.mock('./JourneyMap',()=>({default:'JourneyMap'}));
vi.mock('./CommunityPanels',()=>({BaselinePanel:'BaselinePanel',MissionPanel:'MissionPanel',RankingPanel:'RankingPanel',RewardPanel:'RewardPanel',PanelPreview:'PanelPreview'}));

(globalThis as any).IS_REACT_ACT_ENVIRONMENT=true;
let rendered:ReactTestRenderer|undefined;
afterEach(async()=>{if(rendered)await act(()=>rendered!.unmount());rendered=undefined;});
const p={active:true,phase:'recording',tripId:'test',events:[],duration:'02:15',route:null,trips:[],profile:{role:'user',nickname:'테스트'},collectionMode:'user',backgroundRunning:true,ready:true} as unknown as ServiceProps;

it.each([568,667,844,932])('keeps a usable reopen toggle through repeated collapse at height %i',async height=>{
 windowSize.height=height;
 await act(()=>{rendered=create(<JourneyInfoPanel p={p}/>);});
 for(let i=0;i<5;i++){
  const toggle=()=>rendered!.root.findByProps({testID:'journey-info-toggle'});
  expect(toggle().props.accessibilityState.expanded).toBe(true);
  await act(()=>toggle().props.onPress());
  expect(toggle().props.accessibilityLabel).toBe('이동 정보 펼치기');
  expect(toggle().props.style.minHeight).toBeGreaterThanOrEqual(48);
  expect(JSON.stringify(rendered!.toJSON())).toContain('02:15');
  expect(rendered!.root.findAllByType('ScrollView' as any)).toHaveLength(0);
  await act(()=>toggle().props.onPress());
  expect(rendered!.root.findByProps({testID:'journey-live-speed'})).toBeDefined();
  expect(rendered!.root.findByType('ScrollView' as any).props.style.maxHeight).toBe(height*.30);
 }
});

it('places the panel in the bottom safe area outside the map and restores tabs after stopping',async()=>{
 await act(()=>{rendered=create(<ServiceScreen {...p}/>);});
 const root=()=>rendered!.root;
 expect(root().findAllByProps({accessibilityRole:'tab'})).toHaveLength(0);
 expect(root().findAllByProps({accessibilityLabel:'뒤로'})).toHaveLength(0);
 const panel=root().findByType(JourneyInfoPanel);
 expect(panel.parent?.type).toBe('SafeAreaView');
 expect(panel.parent?.props.edges).toEqual(['bottom']);
 expect(panel.parent?.props.style.flexShrink).toBe(0);
 expect(root().findByType('ActiveJourney' as any).props.showInfo).toBe(false);
 await act(()=>root().findByProps({testID:'journey-info-toggle'}).props.onPress());
 expect(root().findByProps({accessibilityLabel:'이동 정보 펼치기'})).toBeDefined();
 await act(()=>rendered!.update(<ServiceScreen {...p} active={false} phase="stopping"/>));
 expect(root().findAllByProps({accessibilityRole:'tab'})).toHaveLength(0);
 await act(()=>rendered!.update(<ServiceScreen {...p} active={false} phase="idle"/>));
 expect(root().findAllByProps({accessibilityRole:'tab'})).toHaveLength(5);
 expect(root().findAllByType(JourneyInfoPanel)).toHaveLength(0);
});
