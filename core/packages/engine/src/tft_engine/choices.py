"""Option values preserve the shared random tape and all scored Lines."""
import numpy as np
from tft_data.models import DataError
from .planning import best_choice_fit
from .models import ScoredOption, _encode


def selected(result):
    fit=min((f for f in result.comp_fits.values() if f.simulated),key=lambda f:(f.score,f.comp_id))
    line=min(result.line_results[fit.comp_id],key=lambda r:(r.expected_placement,r.line.id))
    return fit,line


def pair(context,changes,*,effects=None,baseline=None,rollouts=None):
    base,before=baseline if baseline is not None else best_choice_fit(context,{},rollouts=rollouts)
    score,after=best_choice_fit(context,changes,effects=effects,rollouts=rollouts)
    if base is None or score is None:
        raise DataError('Choice simulation unavailable')
    before_fit,baseline=selected(before); after_fit,changed=selected(after)
    if any(name not in fit.terms for fit in (before_fit,after_fit) for name in ('item','augment')):
        raise DataError('Choice item or held augment model unavailable')
    differences=np.asarray(baseline.rollout_placements)-np.asarray(changed.rollout_placements)
    error=float(np.std(differences,ddof=1)/np.sqrt(len(differences))) if len(differences)>1 else 0.0
    return base-score,error,before,after,baseline,changed


def expected(context,outcomes,*,baseline=None):
    """Integrate sourced finite outcomes while retaining conditional rollout pairing."""
    from math import isclose, isfinite
    if not outcomes or any(not isfinite(float(row[0])) or row[0]<=0 for row in outcomes) or not isclose(sum(row[0] for row in outcomes),1.0):
        raise DataError('Effect outcomes require positive probabilities summing to one')
    base=baseline if baseline is not None else best_choice_fit(context,{})
    records=[]; score=gain=0.0; paired=None
    for probability,changes,effects,label in outcomes:
        delta,error,before,after,before_line,after_line=pair(context,changes,effects=effects,baseline=base)
        difference=np.asarray(before_line.rollout_placements)-np.asarray(after_line.rollout_placements)
        paired=probability*difference if paired is None else paired+probability*difference
        gain+=probability*delta; score+=probability*selected(after)[0].score
        records.append({'probability':probability,'outcome':label,'placement_gain':delta,'paired_standard_error':error,**evidence(before,after,before_line,after_line)})
    error=float(np.std(paired,ddof=1)/np.sqrt(len(paired))) if len(paired)>1 else 0.0
    return gain,error,score,tuple(records),base,paired


def hold_option(before, *, domain, operation='hold'):
    fit,line=selected(before)
    return ScoredOption(f'{domain}:{operation}',operation,{'operation':operation,'cost_units':'placement',
        'placement_gain':0.0,**evidence(before,before,line,line)},fit.score,0.0,'unchanged_same_seed_baseline')


def evidence(before,after,baseline,changed):
    from hashlib import sha256
    import json
    def bundle(result):
        body={'lines':{id:tuple(r.to_dict() for r in rows) for id,rows in result.line_results.items()},
            'plan':result.plan.to_dict(),'fits':_encode(result.comp_fits)}
        token='sha256:'+sha256(json.dumps(body,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
        return token,body
    before_id,left=bundle(before); after_id,right=bundle(after)
    return {'before':baseline.to_dict(),'after':changed.to_dict(),
        'before_lines':left['lines'],'after_lines':right['lines'],
        'before_plan':left['plan'],'after_plan':right['plan'],
        'before_fits':left['fits'],'after_fits':right['fits'],
        'before_evidence_id':before_id,'after_evidence_id':after_id,
        'before_line_ref':{'comp_id':selected(before)[0].comp_id,'line_id':baseline.line.id,'seed':baseline.seed},
        'after_line_ref':{'comp_id':selected(after)[0].comp_id,'line_id':changed.line.id,'seed':changed.seed}}
