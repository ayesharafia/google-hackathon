import test from 'node:test';
import assert from 'node:assert/strict';
import {connectionConfig,editValue,scopeKey,proposalMatches} from '../../web/js/agent-workspace.js';

test('connection configuration contains an origin and protected file reference, never a supplied secret',()=>{
  const value=connectionConfig('https://example.test/web/workbench.html?token=untrusted');
  assert.equal(value.mcpServers.PhysiCore.env.PHYSICORE_API_URL,'https://example.test');
  assert.deepEqual(value.mcpServers.PhysiCore.args,['-m','physimesh.agent.mcp']);
  assert.ok(!JSON.stringify(value).includes('untrusted'));
  assert.throws(()=>connectionConfig('file:///local/file'));
});
test('explicit numeric input rejects empty, ambiguous and nonfinite quantities',()=>{
  assert.equal(editValue('mission.duration_s','8'),8);
  assert.deepEqual(editValue('cg_body_m','-0.2, 0, 3e-2'),[-.2,0,.03]);
  for(const raw of ['', ' ', '1,2', '8 minutes', 'Infinity','1e999','0x10'])assert.throws(()=>editValue('mass_kg',raw));
  assert.throws(()=>editValue('cg_body_m','1,2'));
});
test('proposal actions require the exact saved project version and writable clean context',()=>{
  const c={generation:1,projectId:'project_a',version:2,connected:true,canWrite:true,dirty:false};
  const p={project_id:'project_a',expected_version:2};assert.equal(proposalMatches(p,c),true);
  for(const altered of [{dirty:true},{canWrite:false},{connected:false},{projectId:'project_b'},{version:3}])assert.equal(proposalMatches(p,{...c,...altered}),false);
  assert.notEqual(scopeKey(c),scopeKey({...c,generation:2}));
  assert.notEqual(scopeKey(c),scopeKey({...c,connected:false}));
});
