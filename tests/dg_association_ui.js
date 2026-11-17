const fs=require('fs'),vm=require('vm'),assert=require('assert');
let script=[...fs.readFileSync('oci/pages/dg.html','utf8').matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)].map(m=>m[1]).join('\n');
script=script.substring(0,script.lastIndexOf('// ── Init'));
const elements={};
const context={document:{getElementById:id=>elements[id]||null,querySelectorAll:()=>[],addEventListener:()=>{}},window:{},console,setTimeout:()=>1,clearTimeout:()=>{},localStorage:{getItem:()=>null}};
vm.createContext(context);vm.runInContext(script,context);
vm.runInContext(`
renderAll=()=>{};renderEditor=()=>{};getCustName=()=>'';
applyConfig({dg_associations:[{module_name:'sales',mode:'existing',database_id:'primary',peer_database_id:'peer',database_admin_password:'ignored'}]});
let first=buildPayload();
if(first.dg_associations[0].peer_database_id!=='peer') throw Error('existing pair not loaded');
if('database_admin_password' in first.dg_associations[0]) throw Error('unknown password preserved');
applyConfig(JSON.parse(JSON.stringify(first)));
if(JSON.stringify(first)!==JSON.stringify(buildPayload())) throw Error('roundtrip changed configuration');
if(fkToApiPath('dg_assoc:sales:tfvars')!=='dg_association_sales/terraform.tfvars') throw Error('preview path');
applyConfig({dg_multi_az:[]});
if(buildPayload().dg_associations.length) throw Error('legacy config kept old associations');
addDgAssociation();
if(!buildPayload().dg_associations[0].is_active_data_guard_enabled) throw Error('active default');
`,context);
console.log('Data Guard UI roundtrip, legacy reset, password filtering, paths, and defaults passed');
vm.runInContext(`
applyConfig({dg_associations:[{module_name:'cli_test',output_format:'both'}]});
if(buildPayload().dg_associations[0].output_format!=='both') throw Error('CLI output choice lost');
if(fkToApiPath('dg_assoc:cli_test:cli_script')!=='dg_association_cli_test/cli/run.sh') throw Error('CLI script path');
if(fkToApiPath('dg_assoc:cli_test:cli_request')!=='dg_association_cli_test/cli/request.json') throw Error('CLI JSON path');
`,context);
