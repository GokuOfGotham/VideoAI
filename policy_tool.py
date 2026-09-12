"""Export VideoAI's shared prompt or validate an edit plan without API charges."""
import argparse
import json
from pathlib import Path
from videoai_policy import policy_prompt, review_template, validate_plan, validate_script, ProductionPolicyError

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['prompt','template','check'])
    p.add_argument('file',nargs='?');p.add_argument('--format',choices=['long','short'],default='short')
    p.add_argument('--content-type',choices=['gameplay','documentary','lore','other'],default='documentary')
    p.add_argument('--duration',type=float)
    a=p.parse_args()
    try:
        if a.action=='prompt': print(policy_prompt(content_type=a.content_type,video_format=a.format))
        elif a.action=='template':print(json.dumps({'production_review':review_template(a.content_type,a.format)},indent=2))
        else:
            if not a.file:p.error('check requires a JSON script/config file')
            data=json.loads(Path(a.file).read_text(encoding='utf-8-sig'))
            fn=validate_script if any(k in data for k in ['narration_script','full_voiceover_text']) else validate_plan
            print(json.dumps(fn(data,duration=a.duration if a.duration is not None else data.get('duration')),indent=2))
    except (ProductionPolicyError, OSError, ValueError) as exc:
        print(json.dumps({'status':'failed','error':str(exc)}));return 1
    return 0
if __name__=='__main__':raise SystemExit(main())
