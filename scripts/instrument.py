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
                         '    if (check) {\n        demo_trace::declaration_scope tracing(v.get_name());')
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
    path.write_text(text)
print('Kernel logging installed in the separate Lean checkout.')
