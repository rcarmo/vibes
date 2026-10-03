import { test, expect } from 'bun:test';
import { readFileSync } from 'node:fs';
import { agentRequestDetails } from '../../src/vibes/static/js/components/agent-request-details.js';
const native = rawInput => ({tool_call:{title:'Copilot tool permission',description:JSON.stringify(rawInput),rawInput}});

test('native plan read is an action, not a JSON description',()=>{
 const raw={kind:'custom-tool',toolName:'plan',toolDescription:'Read/write the plan',args:{action:'read'},toolCallId:'synthetic'};
 const result=agentRequestDetails(native(raw));
 expect(result.title).toBe('Read conversation plan');
 expect(result.explanation).toBe('Read the shared plan for this conversation.');
 expect(result.fields).toEqual([]);
 expect(JSON.parse(result.technical)).toEqual(raw);
});
test('plan write preserves proposed content and revision',()=>{
 const result=agentRequestDetails(native({kind:'custom-tool',toolName:'plan',args:{action:'write',markdown:'- [ ] Review',expected_revision:3}}));
 expect(result.title).toBe('Update conversation plan');
 expect(result.fields).toEqual([{label:'markdown',value:'- [ ] Review'},{label:'expected_revision',value:'3'}]);
});
test('MCP identity and structured args stay visible',()=>{
 const result=agentRequestDetails(native({kind:'mcp',serverName:'example',toolName:'example-lookup',args:{query:'fixture',filters:{limit:1}}}));
 expect(result.title).toBe('Run example-lookup');
 expect(result.fields[0]).toEqual({label:'MCP server',value:'example'});
 expect(result.fields[2].value).toContain('"limit": 1');
});
test('native file and shell unions are parsed',()=>{
 expect(agentRequestDetails(native({kind:'read',path:'note.txt',intention:'Read input'})).paths).toEqual(['note.txt']);
 expect(agentRequestDetails(native({kind:'shell',fullCommandText:'echo test'})).command).toBe('echo test');
 expect(agentRequestDetails(native({kind:'custom-tool',toolName:'vibes_attach_file',args:{path:'report.md'}})).title).toBe('Attach file');
});
test('full CLI text takes precedence and warnings are not hidden in technical details',()=>{
 const command='Write-Output "'+ 'x'.repeat(900)+'"\nGet-ChildItem';
 const result=agentRequestDetails(native({kind:'shell',command:'truncated',fullCommandText:command,
   possiblePaths:['C:\\work\\report.txt'],resolvedWorkingDirectory:'C:\\work',hasWriteFileRedirection:true,
   requestSandboxBypass:true,requestSandboxBypassReason:'Needs broader filesystem access',warning:'Check output target'}));
 expect(result.command).toBe(command);
 expect(result.paths).toEqual(['C:\\work\\report.txt']);
 expect(result.fields).toContainEqual({label:'Working directory',value:'C:\\work'});
 expect(result.warnings).toEqual(['Check output target','Needs broader filesystem access','This command redirects output to a file.']);
});
test('legacy ACP payload remains readable and never renders objects',()=>{
 const result=agentRequestDetails({tool_call:{title:'Legacy tool',rawInput:{command:'echo hi'},description:'Run test'}});
 expect(result.title).toBe('Legacy tool');expect(result.command).toBe('echo hi');expect(result.technical).toBeNull();
 expect(agentRequestDetails({tool_call:{title:{invalid:true},rawInput:{command:{unexpected:true}}}}).command).toBeNull();
});
test('composer contains no agent-capability diagnostics',()=>{
 const source=readFileSync(new URL('../../src/vibes/static/js/components/compose-box.js',import.meta.url),'utf8');
 expect(source).not.toContain('AgentCapabilities');
});
