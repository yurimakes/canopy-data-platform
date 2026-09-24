// All visual parts are clipped from the unmodified user-supplied character sheet.
// Coordinates are in the original 1536 × 1024 sheet, not regenerated illustrations.
export type SheetPart={path:string;pivot:[number,number]};
export const sheetParts:Record<string,SheetPart>={
 frontBody:{pivot:[113,246],path:'M84 239 C103 235 128 236 141 242 C153 247 158 258 160 274 L158 295 L149 314 L138 330 L123 329 L113 321 L100 330 L85 324 L75 308 L69 287 L73 261 Z'},
 legShaft:{pivot:[61,638],path:'M46 629 C51 625 75 630 81 639 L78 662 C76 672 43 672 37 663 Z'},
 footFront:{pivot:[458,625],path:'M437 601 C452 592 477 594 490 604 L495 618 C505 633 506 651 496 663 C480 675 429 676 412 664 C405 656 408 639 416 626 L420 614 Z'},
 footSide:{pivot:[583,625],path:'M559 595 C575 597 598 597 614 593 L619 614 C620 629 626 643 617 654 C600 670 552 674 532 666 C520 660 520 651 529 640 L545 627 L553 613 Z'},
 fist:{pivot:[837,520],path:'M812 473 C813 457 827 449 839 453 C850 446 861 454 866 461 C879 462 883 476 877 488 L868 505 L853 520 L826 522 C811 513 805 494 812 473 Z'},
 pointHand:{pivot:[916,520],path:'M900 485 C907 475 918 474 929 464 L945 450 C951 446 958 448 957 455 L946 473 L932 485 C946 483 951 491 945 498 L934 518 L920 529 L903 524 L890 508 C885 496 891 488 900 485 Z'},
 thumbHand:{pivot:[989,519],path:'M978 484 L989 478 L996 451 C998 441 1005 435 1011 442 L1012 465 L1009 480 C1024 475 1036 481 1037 490 L1037 510 C1033 524 1018 530 1001 527 L982 522 L970 511 L969 494 Z'},
 okayHand:{pivot:[1076,519],path:'M1065 480 C1067 464 1075 452 1086 450 C1097 447 1103 454 1098 464 L1091 475 L1103 473 C1110 475 1115 484 1113 492 L1124 490 C1134 495 1133 505 1124 510 L1111 524 L1094 531 L1077 529 L1062 519 L1054 504 Z'},
 sparkle:{pivot:[1474,474],path:'M1474 441 C1478 460 1484 466 1505 474 C1485 481 1479 489 1473 505 C1468 488 1461 481 1445 476 C1464 467 1470 459 1474 441 Z'},
 heartFx:{pivot:[1200,633],path:'M1200 610 C1177 586 1155 605 1163 629 C1169 645 1186 659 1202 669 C1217 655 1237 639 1242 619 C1246 599 1216 589 1200 610 Z'},
 speech:{pivot:[1450,629],path:'M1424 591 C1442 587 1468 589 1485 591 C1510 596 1524 616 1513 640 C1505 660 1478 660 1439 660 L1418 673 L1420 655 C1402 651 1392 637 1396 617 C1398 604 1409 594 1424 591 Z'},
 head:{pivot:[961,201],path:'M960 111 C938 108 917 117 907 133 C899 147 900 170 910 187 C921 201 940 205 960 205 C984 205 1004 197 1011 180 C1018 163 1015 143 1005 129 C995 117 979 112 960 111 Z M906 143 C897 142 893 151 893 164 C893 176 897 183 906 186 L910 180 L909 147 Z M1011 143 C1019 145 1020 154 1020 165 C1020 176 1017 181 1011 184 L1008 177 L1009 148 Z M962 113 L959 104 C932 106 914 86 916 54 C941 46 970 64 969 94 L970 104 C978 86 997 76 1015 74 C1016 96 996 109 975 109 L974 114 Z'},
 wink:{pivot:[833,201],path:'M827 106 C811 96 795 83 794 57 C817 57 838 77 839 94 C852 84 872 79 886 80 C882 99 865 109 848 113 C869 116 884 129 888 145 L894 149 L896 174 L886 185 C876 199 858 204 834 204 C810 204 792 199 783 186 L776 184 L769 175 L769 151 L777 141 C783 125 798 115 817 111 Z'},
 happy:{pivot:[1204,202],path:'M1198 111 C1181 99 1162 82 1160 55 C1181 56 1203 77 1206 95 C1219 85 1239 79 1253 82 C1249 100 1230 109 1218 115 C1240 118 1251 130 1255 147 L1262 150 L1264 173 L1256 185 C1244 201 1227 205 1205 206 C1180 204 1163 199 1153 186 L1145 183 L1141 172 L1142 151 L1150 143 C1156 125 1172 117 1190 113 Z'},
 sideHead:{pivot:[289,237],path:'M289 112 C264 100 243 86 241 53 C267 54 291 72 305 97 L310 116 C336 118 351 132 358 151 C367 171 363 199 350 216 C337 234 315 242 286 241 C258 241 239 231 233 210 C228 191 232 165 241 145 C250 125 269 119 288 120 Z'},
 torso:{pivot:[190,450],path:'M169 443 C181 437 199 439 207 444 C219 446 229 452 236 465 L243 490 C245 509 239 530 233 547 L224 556 L207 559 L197 548 L186 554 L171 560 L156 554 C147 545 145 530 143 514 C137 492 141 469 150 455 Z'},
 sideTorso:{pivot:[277,245],path:'M264 246 C251 254 245 274 246 293 C247 309 254 320 270 327 L288 327 L298 315 L291 299 L286 272 L296 254 L283 246 Z'},
 arm:{pivot:[391,456],path:'M383 445 C389 438 396 441 402 451 L414 470 L427 495 L423 506 L406 513 L393 503 L385 481 L379 464 C375 454 377 448 383 445 Z'},
 upperArm:{pivot:[391,456],path:'M383 445 C389 438 396 441 402 451 L414 470 L419 487 L400 497 L388 484 L379 464 C375 454 377 448 383 445 Z'},
 foreArm:{pivot:[402,480],path:'M385 477 L408 467 L427 495 L423 506 L406 513 L393 503 Z'},
 armAlt:{pivot:[463,457],path:'M454 445 C461 440 469 441 474 451 L488 472 L507 493 L509 505 L490 517 L477 509 L463 489 L454 474 L449 457 Z'},
 palm:{pivot:[748,521],path:'M736 528 C724 525 716 514 712 505 L705 481 C704 474 709 470 714 474 L724 486 L719 465 C718 456 724 452 729 457 L738 474 L735 455 C735 447 742 443 747 449 L751 470 L756 451 C758 444 765 444 769 450 L767 476 L776 461 C781 455 788 460 785 468 L778 490 C784 484 791 485 791 492 C786 507 772 525 760 529 Z'},
 hand:{pivot:[416,509],path:'M407 501 L423 500 C430 504 433 514 429 525 L425 534 L418 536 L414 533 L408 536 L404 531 L401 520 Z'},
 legL:{pivot:[74,595],path:'M63 582 C74 578 83 584 91 593 L96 608 L87 636 L78 664 C82 674 80 684 70 689 C57 696 36 693 28 689 C23 684 27 671 34 662 L43 630 L53 601 Z'},
 legR:{pivot:[137,594],path:'M125 588 C130 579 143 579 151 585 L160 600 L173 628 L188 658 C196 670 198 681 186 686 C174 692 157 691 145 685 L139 675 L131 651 L121 623 L119 606 Z'},
 thighL:{pivot:[74,595],path:'M63 582 C74 578 83 584 91 593 L96 608 L83 638 C79 650 52 645 45 634 L53 601 Z'},
 shinL:{pivot:[61,638],path:'M44 631 L86 642 L78 664 C82 674 80 684 70 689 C57 696 36 693 28 689 C23 684 27 671 34 662 Z'},
 thighR:{pivot:[137,594],path:'M125 588 C130 579 143 579 151 585 L160 600 L176 634 L175 646 L135 649 L121 623 L119 606 Z'},
 shinR:{pivot:[155,637],path:'M130 638 L170 627 L188 658 C196 670 198 681 186 686 C174 692 157 691 145 685 L139 675 Z'},
};
function shiftedPath(path:string,dx:number,dy:number){let n=0;return path.replace(/-?\d+(?:\.\d+)?/g,v=>String(Number(v)+(n++%2?dy:dx)));}
const headShell=sheetParts.head.path.split(' M962')[0];
sheetParts.happy.path=shiftedPath(headShell,245,1)+' M1207 113 L1205 104 C1177 107 1159 88 1160 55 C1186 48 1215 65 1214 96 L1215 104 C1223 88 1247 80 1264 80 C1262 100 1245 109 1220 110 L1219 115 Z';
sheetParts.wink.path=shiftedPath(headShell,-128,0)+' M833 112 L831 106 C807 104 794 84 794 57 C816 52 840 75 839 94 L840 105 C851 87 871 79 887 80 C884 101 866 110 846 109 L845 114 Z';
export type SheetLayer={part:string;x:number;y:number;angle:number;scale:number;flip?:boolean;opacity?:number;widthScale?:number};
export function sheetTransform(layer:SheetLayer){const p=sheetParts[layer.part].pivot;return `translate(${layer.x} ${layer.y}) rotate(${layer.angle}) scale(${(layer.flip?-layer.scale:layer.scale)*(layer.widthScale??1)} ${layer.scale}) translate(${-p[0]} ${-p[1]})`;}
export const sheetExpressions=[
 {id:'neutral',label:'기본',part:'head'}, {id:'wink',label:'윙크 · 미소',part:'wink'},
 {id:'joy',label:'윙크 · 활짝',part:'joy'}, {id:'happy',label:'눈웃음',part:'happy'},
 {id:'surprised',label:'놀람',part:'surprised'}, {id:'sad',label:'걱정 · 슬픔',part:'sad'},
 {id:'angry',label:'화남',part:'angry'}, {id:'calm',label:'차분함',part:'calm'},
 {id:'love',label:'하트 눈',part:'love'}, {id:'dizzy',label:'어지러움',part:'dizzy'},
 {id:'disappointed',label:'시무룩',part:'disappointed'}, {id:'thinking',label:'생각',part:'thinking'},
] as const;
export type SheetExpression=typeof sheetExpressions[number]['id'];
for(const [id,cx,dy] of [['joy',1084,0],['surprised',1332,1],['sad',1460,2],['angry',833,176],['calm',959,176],['love',1084,178],['dizzy',1208,179],['disappointed',1333,179],['thinking',1461,179]] as const){
 const dx=cx-961;
 let path=shiftedPath(sheetParts.head.path,dx,dy);
 // Bottom-row leaves begin higher than the top-row template; preserve the complete blades.
 if(dy>100)path=shiftedPath(headShell,dx,dy)+shiftedPath(sheetParts.head.path.slice(sheetParts.head.path.indexOf(' M962')),dx,dy-9)+` M${cx-4} ${110+dy-10} L${cx+10} ${110+dy-10} L${cx+10} ${116+dy} L${cx-4} ${116+dy} Z`;
 sheetParts[id]={pivot:[cx,201+dy],path};
}
export {sheetPose,sheetMotions,sheetHands} from './sheetMotion';
export type {SheetOptions} from './sheetMotion';
