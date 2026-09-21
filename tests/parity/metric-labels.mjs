// Reference display contract, independent of product implementation imports.
export function byteLabel(value){
 if(typeof value!=='number'||!Number.isFinite(value)||value<0)throw new Error('Invalid canonical byte value');
 if(value===0)return '0B';
 const units=['B','K','M','G','T'];let index=0;
 while(value>=1024&&index<units.length-1){value/=1024;index++;}
 return `${value.toFixed(index===0||value>=10?0:1)}${units[index]}`;
}
