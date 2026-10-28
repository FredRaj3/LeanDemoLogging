#!/usr/bin/env python3
"""Add observation-only logging to the pinned Lean source checkout."""
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "lean4/src/kernel"
shutil.copyfile(ROOT / "instrumentation/demo_trace.h", SRC / "demo_trace.h")


def replace_once(text, old, new):
    assert text.count(old) == 1, f"Expected one occurrence: {old[:100]}"
    return text.replace(old, new, 1)


def wrap(text, signature, result_type, trace_arguments):
    start = text.index(signature + " {")
    body_start = start + len(signature) + 2
    # Kernel functions end at a closing brace in column zero.
    body_end = text.index("\n}", body_start)
    body = text[body_start:body_end]
    wrapped = ("\n    demo_trace::call trace(" + trace_arguments + ");\n"
               "    return trace.finish([&]() -> " + result_type + " {" + body +
               "\n    }());")
    return text[:body_start] + wrapped + text[body_end:]


def in_function(text, signature, old, new, count=1):
    start = text.index(signature)
    end = text.index("\n}", start)
    body = text[start:end]
    assert body.count(old) == count, f"Expected {count} of {old[:80]} in {signature}"
    return text[:start] + body.replace(old, new) + text[end:]


def label(text, signature, call, purpose, count=1):
    """Record why the kernel makes `call`. Its arguments must make no traced calls."""
    return in_function(text, signature, call, f'(demo_trace::purpose("{purpose}"), {call})', count)


# (function, call, purpose): the reason each traced call is made, at the line that makes it.
TYPE_CHECKER_PURPOSES = [
    ('type_checker::ensure_sort_core(', 'whnf(e)', 'reduce to expose a sort'),
    ('type_checker::ensure_pi_core(', 'whnf(e)', 'reduce to expose a function type'),
    ('type_checker::infer_lambda(', 'infer_type_core(d, infer_only)', 'binder type must be a type'),
    ('type_checker::infer_lambda(', 'infer_type_core(instantiate_rev(e, fvars.size(), fvars.data()), infer_only)',
     'type of the body'),
    ('type_checker::infer_pi(', 'infer_type_core(d, infer_only)', 'binder type must be a type'),
    ('type_checker::infer_pi(', 'infer_type_core(e, infer_only)', 'body must be a type'),
    ('type_checker::infer_app(', 'infer_type_core(app_fn(e), infer_only)', 'type of the function'),
    ('type_checker::infer_app(', 'infer_type_core(app_arg(e), infer_only)', 'type of the argument'),
    ('type_checker::infer_app(', 'infer_type_core(f, true)', 'type of the function'),
    ('type_checker::infer_let(', 'infer_type_core(type, infer_only)', 'declared type must be a type'),
    ('type_checker::infer_let(', 'infer_type_core(val, infer_only)', 'type of the value'),
    ('type_checker::infer_let(', 'is_def_eq(val_type, type)', 'value has the declared type'),
    ('type_checker::infer_let(', 'infer_type_core(instantiate_rev(e, fvars.size(), fvars.data()), infer_only)',
     'type of the body'),
    ('type_checker::whnf_fvar(', 'whnf_core(*v, cheap_rec, cheap_proj)', "use the variable's let value"),
    ('type_checker::whnf_core(', 'whnf_core(*m, cheap_rec, cheap_proj)', 'reduce after taking the projection'),
    ('type_checker::whnf_core(', 'whnf_core(f0, cheap_rec, cheap_proj)', 'reduce the function part'),
    ('type_checker::whnf_core(', 'whnf_core(mk_rev_app(instantiate(binding_body(f), m, args.data() + (num_args - m)), '
     'num_args - m, args.data()),\n                          cheap_rec, cheap_proj)',
     'substitute the arguments (beta)'),
    ('type_checker::whnf_core(', 'whnf_core(*r, cheap_rec, cheap_proj)', 'reduce after the recursor step'),
    ('type_checker::whnf_core(', 'whnf_core(mk_rev_app(f, args.size(), args.data()), cheap_rec, cheap_proj)',
     'reduce with the reduced function part'),
    ('type_checker::whnf_core(', 'whnf_core(instantiate(let_body(e), let_value(e)), cheap_rec, cheap_proj)',
     'substitute the let value (zeta)'),
    ('type_checker::whnf(', 'whnf_core(t)', 'reduce without unfolding'),
    ('type_checker::whnf(', 'unfold_definition(t1)', 'unfold the head definition'),
    ('type_checker::is_def_eq_binding(', 'is_def_eq(var_t_type, *var_s_type)', 'compare binder types'),
    ('type_checker::is_def_eq_binding(', 'is_def_eq(instantiate_rev(t, subst.size(), subst.data()),\n'
     '                     instantiate_rev(s, subst.size(), subst.data()))', 'compare bodies'),
    ('type_checker::is_def_eq_args(', 'is_def_eq(app_arg(t), app_arg(s))', 'compare arguments'),
    ('type_checker::is_def_eq_app(', 'is_def_eq(t_fn, s_fn)', 'compare functions'),
    ('type_checker::is_def_eq_app(', 'is_def_eq(t_args[i], s_args[i])', 'compare arguments'),
    ('type_checker::is_def_eq_proof_irrel(', 'infer_type(t)', 'type of the left side (proof irrelevance)'),
    ('type_checker::is_def_eq_proof_irrel(', 'is_prop(t_type)', 'is that type a proposition?'),
    ('type_checker::is_def_eq_proof_irrel(', 'infer_type(s)', 'type of the right side'),
    ('type_checker::is_def_eq_proof_irrel(', 'is_def_eq(t_type, s_type)', 'proofs of the same proposition are equal'),
    ('type_checker::is_def_eq_core(', 'whnf(t)', 'evaluate to Bool.true'),
    ('type_checker::is_def_eq_core(', 'whnf_core(t, false, true)', 'reduce left side without unfolding'),
    ('type_checker::is_def_eq_core(', 'whnf_core(s, false, true)', 'reduce right side without unfolding'),
    ('type_checker::is_def_eq_core(', 'whnf_core(t_n)', 'reduce left side, including projections'),
    ('type_checker::is_def_eq_core(', 'whnf_core(s_n)', 'reduce right side, including projections'),
    ('type_checker::is_def_eq_core(', 'is_def_eq_core(t_n_n, s_n_n)', 'compare the reduced sides'),
]


path = SRC / "type_checker.cpp"
text = path.read_text()
if '#include "kernel/demo_trace.h"' not in text:
    text = replace_once(text, '#include "kernel/type_checker.h"',
                        '#include "kernel/type_checker.h"\n#include "kernel/demo_trace.h"')
    for signature, result, args in [
        ('expr type_checker::infer_type_core(expr const & e, bool infer_only)', 'expr',
         'infer_only ? "infer" : "check", m_lctx, e'),
        ('expr type_checker::whnf(expr const & e)', 'expr', '"whnf", m_lctx, e'),
        ('expr type_checker::whnf_core(expr const & e, bool cheap_rec, bool cheap_proj)', 'expr',
         '"whnf_core", m_lctx, e'),
        ('optional<expr> type_checker::unfold_definition_core(expr const & e)', 'optional<expr>',
         '"unfold", m_lctx, e'),
        ('bool type_checker::is_def_eq_core(expr const & t, expr const & s)', 'bool',
         '"defeq", m_lctx, t, &s'),
    ]:
        text = wrap(text, signature, result, args)
    # Log additions after the original code has installed them in the context.
    lines = text.splitlines()
    revised = []
    for line in lines:
        revised.append(line)
        if 'expr fvar ' in line and 'm_lctx.mk_local_decl' in line:
            revised.append('        demo_trace::context(m_lctx, fvar);')
        if 'subst.push_back(m_lctx.mk_local_decl' in line:
            revised.append('            demo_trace::context(m_lctx, subst.back());')
    text = '\n'.join(revised) + '\n'
    text = replace_once(text, '        expr d_type = binding_domain(f_type);',
                        '        expr d_type = binding_domain(f_type);\n'
                        '        demo_trace::application(m_lctx, a_type, d_type);')
    for cache in ['m_infer_type[infer_only]', 'm_whnf', 'm_whnf_core']:
        old = f'    if (it != m_st->{cache}.end())\n        return it->second;'
        new = (f'    if (it != m_st->{cache}.end()) {{\n'
               f'        demo_trace::emit("cache", {{{{"name", "{cache}"}}}});\n'
               '        return it->second;\n    }')
        text = replace_once(text, old, new)
    for signature, call, purpose in TYPE_CHECKER_PURPOSES:
        text = label(text, signature, call, purpose)
    text = label(text, 'type_checker::infer_app(', 'is_def_eq(a_type, d_type)', 'argument has the expected type', 2)
    # Lazy delta reduction unfolds one or both sides, then reduces the result.
    for side, var in [('left', 't_n'), ('right', 's_n')]:
        text = in_function(text, 'type_checker::lazy_delta_reduction_step(',
                           f'whnf_core(*unfold_definition({var}), false, true)',
                           f'whnf_core(demo_trace::purpose("reduce after unfolding", '
                           f'*(demo_trace::purpose("unfold {side} side"), unfold_definition({var}))), false, true)', 3)
    path.write_text(text)

path = SRC / "environment.cpp"
text = path.read_text()
if '#include "kernel/demo_trace.h"' not in text:
    text = replace_once(text, '#include "kernel/type_checker.h"',
                        '#include "kernel/type_checker.h"\n#include "kernel/demo_trace.h"')
    start = text.index('environment environment::add_theorem(')
    end = text.index('\nenvironment environment::add_opaque(', start)
    block = text[start:end]
    block = replace_once(block, '    if (check) {',
                         '    if (check) {\n        demo_trace::declaration_scope tracing(*this, v.get_name());')
    block = replace_once(block, '        check_constant_val(*this, v.to_constant_val(), checker);',
                         '        demo_trace::phase("statement");\n'
                         '        check_constant_val(*this, v.to_constant_val(), checker);')
    block = replace_once(block, '        expr val_type = checker.check(val, v.get_lparams());',
                         '        demo_trace::phase("proof");\n'
                         '        expr val_type = checker.check(val, v.get_lparams());\n'
                         '        demo_trace::phase("comparison");')
    block = replace_once(block, '            throw definition_type_mismatch_exception(*this, d, val_type);',
                         '            throw definition_type_mismatch_exception(*this, d, val_type);\n'
                         '        tracing.accepted();')
    text = text[:start] + block + text[end:]
    text = label(text, 'static void check_constant_val(environment const & env, constant_val const & v, type_checker',
                 'checker.check(v.get_type(), v.get_lparams())', 'check the statement')
    for call, purpose in [('checker.is_prop(type)', "statement's type must be Prop"),
                          ('checker.check(val, v.get_lparams())', 'check the proof'),
                          ('checker.is_def_eq(val_type, type)', "proof's type matches the statement")]:
        text = label(text, 'environment environment::add_theorem(', call, purpose)
    path.write_text(text)
print('Kernel logging installed in the separate Lean checkout.')
