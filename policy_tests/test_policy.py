import ast
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from videoai_policy import *

def valid(kind='documentary'):
    review=review_template(kind)
    review.update(hook='The valve is open as gas escapes; narration explains the threat.',first_payoff_seconds=6,
                  first_payoff='Show why restarting the isolated pump released gas.',
                  pacing_review='Removed greeting and repeated setup; preserved the pump explanation.')
    return {'title':'Why the pump was unsafe','narration_script':'The missing valve left the pump unsafe to restart.',
            'production_review':review,'scenes':[{'duration_est':12,'scene_text':'The missing valve left the pump unsafe to restart.'}]}

def isolated(name, file, globals_dict):
    tree=ast.parse((ROOT/file).read_text(encoding='utf-8'))
    node=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name==name)
    node.decorator_list=[]
    # Execute the actual checked-in function without importing GPU/voice dependencies.
    module=ast.Module(body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0),node],type_ignores=[])
    ns=dict(globals_dict);exec(compile(ast.fix_missing_locations(module),str(ROOT/file),'exec'),ns)
    return ns[name]

class PolicyChecks(unittest.TestCase):
    def test_valid_and_current_policy_stamp(self):
        out=checked_script(valid(),duration=60)
        self.assertEqual(out['production_policy_check']['policy_version'],load_policy()['version'])
        self.assertNotIn('production_policy_check',valid())
    def test_blank_template_rejected(self):
        with self.assertRaises(ProductionPolicyError):validate_plan({'production_review':review_template()})
    def test_missing_review_rejected(self):
        with self.assertRaisesRegex(ProductionPolicyError,'Missing production_review'):validate_plan({})
    def test_delay_and_nonfinite_rejected(self):
        for key,value in [('hook_start_seconds',2),('first_payoff_seconds',16),('first_payoff_seconds',float('nan')),('first_payoff_seconds',True),('first_payoff_seconds',float('inf'))]:
            with self.subTest(key=key,value=value):
                d=valid();d['production_review'][key]=value
                with self.assertRaises(ProductionPolicyError):validate_script(d,duration=60)
    def test_payoff_must_be_inside_actual_runtime(self):
        with self.assertRaises(ProductionPolicyError):validate_script(valid(),duration=5)
    def test_audio_modes_and_overrides(self):
        d=valid('gameplay');validate_plan(d,duration=60)
        d['production_review']['audio_mode']='cedar'
        with self.assertRaises(ProductionPolicyError):validate_plan(d)
        d['production_review']['overrides']={'audio':{'reason':'Narrated gameplay breakdown requested.','user_request':'Use Cedar to explain the combat in this edit.'}}
        validate_plan(d)
        d['production_review']['overrides']['audio']['user_request']=''
        with self.assertRaises(ProductionPolicyError):validate_plan(d)
    def test_explicit_trailer_and_delayed_payoff(self):
        d=valid();r=d['production_review'];r['standalone']=False;r['first_payoff_seconds']=20
        r['overrides']={k:{'reason':'Requested theatrical trailer timing.','user_request':'Make a trailer with the reveal at twenty seconds and link the main film.'} for k in ['standalone','payoff']}
        d['narration_script']='Watch the full video to explore the aftermath.'
        validate_script(d,duration=60)
    def test_obvious_text_conflicts(self):
        for text in ['Welcome back to our channel.','In today\'s video, we explain the pump.','The pump failed. [pause 2.0s] Gas escaped.','Watch the full video to see the result.']:
            d=valid();d['narration_script']=text
            with self.subTest(text=text), self.assertRaises(ProductionPolicyError):validate_script(d,duration=60)
    def test_retained_setup_needs_reason(self):
        d=valid();d['scenes'][0]['role']='redundant_travel'
        with self.assertRaises(ProductionPolicyError):validate_plan(d)
        d['scenes'][0]['editorial_reason']='Shows the only escape route before it becomes blocked.'
        validate_plan(d)
    def test_prompt_contains_rules_and_schema_for_every_profile(self):
        for kind in ['gameplay','documentary','lore']:
            text=policy_prompt(content_type=kind,video_format='long')
            self.assertIn('production_review',text);self.assertIn('APV is not completion rate',text)
            for rule in load_policy()['rules']:self.assertIn(rule,text)

class ProviderChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        dotenv=types.ModuleType('dotenv');dotenv.load_dotenv=lambda *a,**k:None
        requests=types.ModuleType('requests');requests.post=Mock(side_effect=AssertionError('Unexpected network'))
        spec=importlib.util.spec_from_file_location('tested_script_generator',ROOT/'script_generator.py')
        cls.sg=importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules,{'dotenv':dotenv,'requests':requests}):spec.loader.exec_module(cls.sg)
    def test_selected_provider_receives_same_rules(self):
        for provider,method in [('openai','_call_openai_chat'),('gemini','_call_gemini_chat'),('deepseek','_call_openai_compatible')]:
            with patch.object(self.sg,method,return_value=valid()) as call:
                out=self.sg.generate_video_script('Unsafe pump',60,provider,content_type='lore')
            self.assertIn('production_review',call.call_args.args[0]);self.assertIn(load_policy()['rules'][0],call.call_args.args[0]);self.assertIn('production_policy_check',out)
    def test_invalid_provider_output_never_accepted(self):
        with patch.object(self.sg,'_call_openai_chat',return_value={'title':'A canned script'}):
            with self.assertRaises(ProductionPolicyError):self.sg.generate_video_script('Unsafe pump')
    def test_all_provider_failure_does_not_use_canned_script(self):
        with patch.object(self.sg,'_call_openai_chat',return_value=None),patch.object(self.sg,'_call_gemini_chat',return_value=None),patch.object(self.sg,'_call_openai_compatible',return_value=None):
            with self.assertRaisesRegex(ProductionPolicyError,'No canned replacement'):self.sg.generate_video_script('Ocean Ranger')
    def test_actual_provider_payloads_have_system_policy(self):
        response=Mock();response.json.return_value={'choices':[{'message':{'content':json.dumps(valid())}}]};response.status_code=200
        for fn,args in [(self.sg._call_openai_chat,('story','model','test-key','topic',60)),(self.sg._call_openai_compatible,('story','model','test-key','https://example.invalid','topic',60))]:
            with patch.object(self.sg.requests,'post',return_value=response) as post:fn(*args)
            self.assertIn(load_policy()['rules'][0],post.call_args.kwargs['json']['messages'][0]['content'])
        response.json.return_value={'candidates':[{'content':{'parts':[{'text':json.dumps(valid())}]}}]}
        with patch.object(self.sg.requests,'post',return_value=response) as post:self.sg._call_gemini_chat('story','model','test-key','topic',60)
        self.assertIn(load_policy()['rules'][0],post.call_args.kwargs['json']['systemInstruction']['parts'][0]['text'])
    def test_aw360_scriptwriter_receives_policy_and_validates(self):
        client=Mock();client.models.generate_content.return_value.text=json.dumps(valid())
        obj=types.SimpleNamespace(client=client)
        fn=isolated('generate_script','aw360/scriptwriter.py',dict(policy_prompt=policy_prompt,checked_script=checked_script,ProductionPolicyError=ProductionPolicyError,json=json))
        fn(obj,{'topic_name':'Pump'})
        self.assertIn(load_policy()['rules'][0],client.models.generate_content.call_args.kwargs['config']['system_instruction'])
        client.models.generate_content.return_value.text='{}'
        with self.assertRaises(ProductionPolicyError):fn(obj,{})
    def test_free_director_records_free_mode_without_paid_voice(self):
        client=Mock();d=valid();r=d['production_review'];r['audio_mode']='explicit_override';r['overrides']={'audio':{'user_request':'Use the free AW360 workflow with Edge narration','reason':'User chose the free audio workflow.'}}
        client.models.generate_content.return_value.text=json.dumps(d)
        fn=isolated('_generate_free_script','aw360/free_director.py',dict(policy_prompt=policy_prompt,checked_script=checked_script,ProductionPolicyError=ProductionPolicyError,json=json))
        fn(types.SimpleNamespace(genai_client=client),'Penguins')
        prompt=client.models.generate_content.call_args.kwargs['config']['system_instruction']
        self.assertIn('Do not switch this workflow to paid narration',prompt)
    def test_cedar_payload_uses_exact_saved_preset(self):
        req=types.SimpleNamespace(post=Mock(return_value=types.SimpleNamespace(content=b'fixture',raise_for_status=lambda:None)))
        fn=isolated('_synthesize_openai_tts','voice_synthesizer.py',dict(json=json,os=types.SimpleNamespace(getenv=lambda _: 'fake-key'),PROJECT_ROOT=ROOT,requests=req))
        with tempfile.TemporaryDirectory() as folder:fn('The missing valve.',str(Path(folder)/'voice.mp3'))
        payload=req.post.call_args.kwargs['json'];preset=json.loads((ROOT/'APPROVED_VOICE_PRESET.json').read_text())
        for key in ['model','voice','speed','instructions']:self.assertEqual(payload[key],preset[key])
    def test_cedar_error_does_not_fallback(self):
        fallback=Mock();fn=isolated('_synthesize_single_chunk','voice_synthesizer.py',dict(_synthesize_openai_tts=Mock(side_effect=RuntimeError('Unavailable')),_synthesize_edge_tts=fallback))
        with self.assertRaises(RuntimeError):fn('A line','out.mp3','openai','cedar','+0Hz','+0%')
        fallback.assert_not_called()

class RendererChecks(unittest.TestCase):
    def test_real_renderer_blocks_missing_plan_before_audio_provider(self):
        from videoai_graphics import renderer
        with tempfile.TemporaryDirectory() as folder,patch.object(renderer,'probe_video',return_value={'width':320,'height':180,'duration':8,'audio_count':1}),patch.object(renderer,'_render') as render:
            with self.assertRaises(ProductionPolicyError):renderer.render_video({},Path(folder)/'source.mp4',Path(folder)/'out.mp4')
            render.assert_not_called()
    def test_natural_audio_render_never_calls_music_provider(self):
        from videoai_graphics import renderer
        commands=[]
        def run(cmd,**kwargs):
            commands.append(cmd);Path(cmd[-1]).write_bytes(b'video');return subprocess.CompletedProcess(cmd,0,'','')
        manifest={'provider':'source','mode':'natural_game','added_music':False,'added_narration':False}
        media={'width':320,'height':180,'duration':8,'audio_count':1}
        with tempfile.TemporaryDirectory() as folder,patch.object(renderer,'_executable',side_effect=lambda x:x),patch.object(renderer,'_run',side_effect=run),patch.object(renderer,'prepare_audio') as paid,patch.object(renderer,'probe_video',return_value={**media,'audio_manifest':manifest}):
            out=renderer._render({'ass':'[Script Info]','duration':8,'caption_count':0,'overlay_count':0},Path(folder)/'out.mp4',['-i','fixture.mp4'],config=valid('gameplay'),source_metadata=True,encoder='cpu',fonts_dir=None,overwrite=False,ffmpeg='ffmpeg',ffprobe='ffprobe',expected_media=media,timeout=30)
        paid.assert_not_called();self.assertEqual(out['audio_manifest'],manifest)
        self.assertNotIn('sidechaincompress',' '.join(commands[0]));self.assertIn('[0:a:0]',' '.join(commands[0]))

if __name__=='__main__':unittest.main()

class PoliticsModeChecks(unittest.TestCase):
    def plan(self):
        d=valid();r=d['production_review'];r['mode']='politics';r['fact_check']='FACT_CHECK.md: one row per claim with source and treatment.'
        d['sources']=[{'outlet':'CBS NEWS','programme':'CBS Mornings','date':'September 10, 2026','url':'https://www.youtube.com/watch?v=3kOmty5rMN4'}]
        d['used_ranges']=[{'export':'main','source':'cbs_dubious','source_in':95.26,'source_out':103.86,'original_audio':True,'speaker':'PRESIDENT TRUMP'},
                          {'export':'main','source':'cbs_dubious','source_in':138.0,'source_out':146.0,'original_audio':False}]
        return d
    def test_valid_politics_plan_is_stamped(self):
        out=validate_plan(self.plan(),duration=60);self.assertEqual(out['mode'],'politics')
        self.assertIn('mode',review_template('documentary','long','politics'))
        self.assertIn('POLITICS MODE IS ON',policy_prompt(mode='politics'))
        self.assertNotIn('POLITICS MODE IS ON',policy_prompt())
        self.assertTrue(any(rule.startswith('POLITICS MODE') for rule in load_policy()['rules']))
    def test_unknown_mode_rejected(self):
        d=self.plan();d['production_review']['mode']='sports'
        with self.assertRaisesRegex(ProductionPolicyError,'Unknown production_review.mode'):validate_plan(d)
        with self.assertRaises(ProductionPolicyError):review_template(mode='sports')
    def test_requires_fact_check_sources_and_ranges(self):
        d=self.plan();d['production_review']['fact_check']=''
        with self.assertRaisesRegex(ProductionPolicyError,'fact_check'):validate_plan(d)
        d=self.plan();d['sources']=[]
        with self.assertRaisesRegex(ProductionPolicyError,'sources'):validate_plan(d)
        d=self.plan();d['sources'][0].pop('url')
        with self.assertRaisesRegex(ProductionPolicyError,'outlet, date and url'):validate_plan(d)
        d=self.plan();d['used_ranges']=[]
        with self.assertRaisesRegex(ProductionPolicyError,'used_ranges'):validate_plan(d)
    def test_excerpt_needs_speaker_and_numeric_bounds(self):
        d=self.plan();d['used_ranges'][0].pop('speaker')
        with self.assertRaisesRegex(ProductionPolicyError,'needs a speaker'):validate_plan(d)
        d=self.plan();d['used_ranges'][0]['source_out']='end'
        with self.assertRaisesRegex(ProductionPolicyError,'numeric source_in and source_out'):validate_plan(d)
        d=self.plan();d['used_ranges'][0]['source_out']=90.0
        with self.assertRaisesRegex(ProductionPolicyError,'source_out <= source_in'):validate_plan(d)
    def test_replayed_range_rejected_within_export_only(self):
        d=self.plan();d['used_ranges'].append({'export':'main','source':'cbs_dubious','source_in':95.26,'source_out':106.0,'original_audio':False})
        with self.assertRaisesRegex(ProductionPolicyError,'shown twice'):validate_plan(d)
        d['used_ranges'][-1]['export']='short';validate_plan(d)
    def test_plans_without_mode_are_unchanged(self):
        out=validate_plan(valid(),duration=60);self.assertIsNone(out['mode'])

if __name__=='__main__':
    unittest.main()
