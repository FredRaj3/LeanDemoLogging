/* Teaching trace for the real Lean kernel. Logging never calls a type checker. */
#pragma once
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>
#include "kernel/local_ctx.h"

namespace lean {
namespace demo_trace {
using fields = std::vector<std::pair<std::string, std::string>>;

inline std::string name_string(name const & n) {
    std::ostringstream out; out << n; return out.str();
}

inline std::string json_string(std::string const & s) {
    std::ostringstream out;
    out << '"';
    for (unsigned char c : s) {
        switch (c) {
        case '"': out << "\\\""; break;
        case '\\': out << "\\\\"; break;
        case '\n': out << "\\n"; break;
        case '\r': out << "\\r"; break;
        case '\t': out << "\\t"; break;
        default:
            if (c < 32) {
                char const * hex = "0123456789abcdef";
                out << "\\u00" << hex[c >> 4] << hex[c & 15];
            } else out << static_cast<char>(c);
        }
    }
    out << '"';
    return out.str();
}

/* A structural printer: it resolves variable names, but performs no reduction.
   The core view retains all constant arguments and universe parameters. */
class printer {
    local_ctx const & m_ctx;
    bool m_core;
    std::vector<std::string> m_bound;
    std::string binder(expr const & e, bool lambda) {
        std::string n = name_string(binding_name(e));
        std::string domain = print(binding_domain(e));
        m_bound.push_back(n);
        std::string body = print(binding_body(e));
        m_bound.pop_back();
        if (!lambda && is_arrow(e)) return "(" + domain + " → " + body + ")";
        std::string left = "(", right = ")";
        if (is_implicit(binding_info(e))) { left = "{"; right = "}"; }
        if (is_strict_implicit(binding_info(e))) { left = "⦃"; right = "⦄"; }
        if (is_inst_implicit(binding_info(e))) { left = "["; right = "]"; }
        return std::string(lambda ? "(fun " : "(∀ ") + left + n + " : " + domain + right
            + (lambda ? " => " : ", ") + body + ")";
    }
public:
    printer(local_ctx const & ctx, bool core): m_ctx(ctx), m_core(core) {}
    std::string print(expr const & e) {
        switch (e.kind()) {
        case expr_kind::FVar:
            if (auto d = m_ctx.find_local_decl(e)) return name_string(d->get_user_name());
            return name_string(fvar_name(e));
        case expr_kind::BVar: {
            nat const & i = bvar_idx(e);
            if (i.is_small() && i.get_small_value() < m_bound.size())
                return m_bound[m_bound.size() - 1 - i.get_small_value()];
            std::ostringstream out; out << i.to_mpz(); return "#" + out.str();
        }
        case expr_kind::MVar: return "?" + name_string(mvar_name(e));
        case expr_kind::Const: {
            std::string s = name_string(const_name(e));
            if (m_core && !is_nil(const_levels(e))) {
                s += ".{"; bool first = true;
                for (auto const & l : const_levels(e)) {
                    std::ostringstream out; out << l;
                    if (!first) s += ", "; first = false; s += out.str();
                }
                s += "}";
            }
            return s;
        }
        case expr_kind::Sort: {
            if (is_zero(sort_level(e))) return "Prop";
            if (is_one(sort_level(e))) return "Type";
            std::ostringstream out; out << sort_level(e); return "Sort " + out.str();
        }
        case expr_kind::App: {
            buffer<expr> args;
            expr const & head = get_app_args(e, args);
            if (!m_core && is_constant(head)) {
                std::string n = name_string(const_name(head));
                if (n == "Eq" && args.size() == 3)
                    return "(" + print(args[1]) + " = " + print(args[2]) + ")";
                if (n == "Function.Injective" && args.size() == 3)
                    return "(Function.Injective " + print(args[2]) + ")";
                if (n == "Function.comp" && args.size() >= 5) {
                    std::string s = "(" + print(args[3]) + " ∘ " + print(args[4]) + ")";
                    for (unsigned i = 5; i < args.size(); ++i) s = "(" + s + " " + print(args[i]) + ")";
                    return s;
                }
            }
            std::string s = "(" + print(head);
            for (auto const & a : args) s += " " + print(a);
            return s + ")";
        }
        case expr_kind::Lambda: return binder(e, true);
        case expr_kind::Pi: return binder(e, false);
        case expr_kind::Let: {
            std::string n = name_string(let_name(e));
            std::string t = print(let_type(e)), v = print(let_value(e));
            m_bound.push_back(n);
            std::string b = print(let_body(e)); m_bound.pop_back();
            return "(let " + n + " : " + t + " := " + v + "; " + b + ")";
        }
        case expr_kind::MData: return print(mdata_expr(e));
        case expr_kind::Proj: {
            std::ostringstream out; out << proj_idx(e);
            return "(" + print(proj_expr(e)) + ")." + out.str();
        }
        case expr_kind::Lit: {
            if (is_nat_lit(e)) { std::ostringstream out; out << lit_value(e).get_nat().to_mpz(); return out.str(); }
            return json_string(lit_value(e).get_string().to_std_string());
        }
        }
        return "<expression>";
    }
};

struct state {
    std::ofstream file;
    std::ostream * out = &std::cerr;
    unsigned depth = 0;
    unsigned sequence = 0;
    unsigned next_call = 0;
    std::string phase = "declaration";
};
inline state *& current() { static thread_local state * s = nullptr; return s; }

inline void emit(char const * event, fields const & values = {}) {
    if (!current()) return;
    auto & s = *current();
    *s.out << "{\"seq\":" << ++s.sequence << ",\"depth\":" << s.depth
           << ",\"event\":" << json_string(event) << ",\"phase\":" << json_string(s.phase);
    for (auto const & kv : values) *s.out << ',' << json_string(kv.first) << ':' << json_string(kv.second);
    *s.out << "}\n";
    s.out->flush();
}

inline void phase(char const * label) {
    if (!current()) return;
    current()->phase = label; emit("phase", {{"name", label}});
}

class declaration_scope {
    state m_state;
    state * m_previous = nullptr;
    bool m_enabled = false;
    bool m_accepted = false;
public:
    explicit declaration_scope(name const & n) {
        char const * filter = std::getenv("LEAN_KERNEL_TRACE_DECL");
        if (!filter || name_string(n) != filter) return;
        char const * path = std::getenv("LEAN_KERNEL_TRACE_FILE");
        if (path && *path) {
            m_state.file.open(path, std::ios::app);
            if (!m_state.file) { std::cerr << "Cannot open kernel trace file: " << path << '\n'; return; }
            m_state.out = &m_state.file;
        }
        m_previous = current(); current() = &m_state; m_enabled = true;
        emit("begin", {{"declaration", name_string(n)}, {"source", "Lean C++ kernel v4.36.0-rc1"}});
    }
    void accepted() { if (m_enabled) { emit("accepted"); m_accepted = true; } }
    ~declaration_scope() {
        if (m_enabled) {
            emit("end", {{"status", m_accepted ? "accepted" : "exception"}});
            current() = m_previous;
        }
    }
};

class call {
    local_ctx const & m_ctx;
    bool m_active;
    bool m_finished = false;
    unsigned m_id = 0;
    void end(fields values) {
        if (!m_active || m_finished) return;
        --current()->depth;
        values.push_back({"call", std::to_string(m_id)});
        emit("return", values); m_finished = true;
    }
public:
    call(char const * operation, local_ctx const & ctx, expr const & e, expr const * other = nullptr):
        m_ctx(ctx), m_active(current() != nullptr) {
        if (!m_active) return;
        m_id = ++current()->next_call;
        fields f = {{"call", std::to_string(m_id)}, {"operation", operation},
                    {"expr", printer(ctx, false).print(e)}, {"core", printer(ctx, true).print(e)}};
        if (other) {
            f.push_back({"other", printer(ctx, false).print(*other)});
            f.push_back({"other_core", printer(ctx, true).print(*other)});
        }
        emit("enter", f); ++current()->depth;
    }
    expr finish(expr const & e) {
        if (m_active) end({{"result", printer(m_ctx, false).print(e)}, {"result_core", printer(m_ctx, true).print(e)}});
        return e;
    }
    bool finish(bool r) { end({{"result", r ? "true" : "false"}}); return r; }
    optional<expr> finish(optional<expr> const & e) {
        if (m_active) {
            if (e) end({{"result", printer(m_ctx, false).print(*e)}, {"result_core", printer(m_ctx, true).print(*e)}});
            else end({{"result", "no unfolding"}});
        }
        return e;
    }
    ~call() { if (m_active && !m_finished) end({{"status", "exception"}}); }
};

inline void context(local_ctx const & ctx, expr const & v) {
    if (!current()) return;
    auto d = ctx.get_local_decl(v);
    fields f = {{"name", name_string(d.get_user_name())}, {"id", name_string(d.get_name())},
                {"type", printer(ctx, false).print(d.get_type())}, {"type_core", printer(ctx, true).print(d.get_type())}};
    if (auto value = d.get_value()) f.push_back({"value", printer(ctx, false).print(*value)});
    emit("context", f);
}

inline void application(local_ctx const & ctx, expr const & actual, expr const & expected) {
    if (current()) emit("argument", {{"actual", printer(ctx, false).print(actual)},
                                     {"expected", printer(ctx, false).print(expected)}});
}
} // namespace demo_trace
} // namespace lean
