import sys
import re

filename = sys.argv[1]

with open(filename, 'r', encoding='utf-8') as f:
    code_lines = [line.rstrip('\n') for line in f]

functions = {}  # key: function name, value: dict with args, body, namespace, scope
variables = {}
in_namespace = [False, None]
pointers = {"sys": {"scope": "public", "arguments": []}}

def split_arguments(arg_str):
    args = []
    current = ''
    quote = None
    for char in arg_str:
        if char in ('"', "'"):
            if quote is None:
                quote = char
            elif quote == char:
                quote = None
        if char == ',' and quote is None:
            args.append(current.strip())
            current = ''
        else:
            current += char
    if current:
        args.append(current.strip())
    return args

def split_on_symbols(text):
    result = []
    token = ''
    quote = None
    i = 0
    while i < len(text):
        c = text[i]
        if c in {'"', "'"}:
            if token:
                result.append(token)
                token = ''
            quote = c
            quoted = c
            i += 1
            while i < len(text):
                quoted += text[i]
                if text[i] == quote:
                    i += 1
                    break
                i += 1
            result.append(quoted)
        elif c in {'.', ','}:
            if token:
                result.append(token)
                token = ''
            i += 1
        elif c in '(){}[]':
            if token:
                result.append(token)
                token = ''
            result.append(c)
            i += 1
        elif c.isspace():
            if token:
                result.append(token)
                token = ''
            i += 1
        else:
            token += c
            i += 1
    if token:
        result.append(token)
    return result

def split_components(input_list):
    output = []
    for line in input_list:
        i = 0
        while i < len(line):
            if line[i] == '(':
                before = line[:i]
                parts = split_on_symbols(before)
                output.extend(parts)
                output.append('(')
                i += 1
                inner = ''
                depth = 1
                quote = None
                while i < len(line):
                    c = line[i]
                    if c in {'"', "'"}:
                        if quote is None:
                            quote = c
                        elif quote == c:
                            quote = None
                    elif c == '(' and quote is None:
                        depth += 1
                    elif c == ')' and quote is None:
                        depth -= 1
                        if depth == 0:
                            break
                    inner += c
                    i += 1
                args = split_arguments(inner)
                output.extend(args)
                output.append(')')
                i += 1
                rest = line[i:]
                output.extend(split_on_symbols(rest))
                break
            i += 1
        else:
            output.extend(split_on_symbols(line))
    return output

def evaluate_expression(expr_tokens, local_vars=None):
    expr = ''.join(expr_tokens)
    try:
        if local_vars:
            for var in sorted(local_vars, key=len, reverse=True):
                expr = re.sub(rf'\b{re.escape(var)}\b', str(local_vars[var]), expr)

        for var in sorted(variables, key=len, reverse=True):
            val = variables[var]["value"] if isinstance(variables[var], dict) else variables[var]
            if local_vars is None or var not in local_vars:
                expr = re.sub(rf'\b{re.escape(var)}\b', str(val), expr)

        return eval(expr)
    except Exception as e:
        if local_vars:
            known_vars = [tok for tok in expr_tokens if tok in local_vars]
            if known_vars:
                return ' '.join(str(local_vars.get(tok, tok)) for tok in expr_tokens)
        return f"[Error evaluating expression: {e}]"

def evaluate_condition(cond_tokens, local_vars=None):
    expr = ''.join(cond_tokens)
    expr = expr.replace("&&", " and ").replace("||", " or ")
    expr = re.sub(r'\bTrue\b', 'True', expr)
    expr = re.sub(r'\bFalse\b', 'False', expr)
    try:
        if local_vars:
            for var in sorted(local_vars, key=len, reverse=True):
                expr = re.sub(rf'\b{re.escape(var)}\b', str(local_vars[var]), expr)
        for var in sorted(variables, key=len, reverse=True):
            val = variables[var]["value"] if isinstance(variables[var], dict) else variables[var]
            if local_vars is None or var not in local_vars:
                expr = re.sub(rf'\b{re.escape(var)}\b', str(val), expr)
        return eval(expr)
    except Exception as e:
        return False

def interpret(a):
    global in_namespace
    i = 0
    namespace_stack = []

    while i < len(a):
        line = a[i]
        split_code = split_components([line])
        if not split_code:
            i += 1
            continue

        # Namespace start
        if len(split_code) > 1 and split_code[1] == "namespace":
            namespace_stack.append((split_code[2], split_code[0]))  # (name, scope)
            in_namespace = [True, split_code[2]]
            i += 1
            continue

        # Namespace end
        if split_code[0] == "}":
            if namespace_stack:
                namespace_stack.pop()
            in_namespace = [False, None] if not namespace_stack else [True, namespace_stack[-1][0]]
            i += 1
            continue

        # Function declaration
        if split_code[0] == "func":
            func_name = split_code[1]
            args = split_code[(split_code.index("(") + 1):(split_code.index(")"))]
            body = []
            i += 1
            while i < len(a) and "}" not in a[i]:
                body.append(a[i])
                i += 1
            i += 1  # Skip closing brace line

            ns_name = in_namespace[1]
            ns_scope = "global"
            if ns_name and ns_name in pointers:
                ns_scope = pointers[ns_name]["scope"]

            functions[func_name] = {
                "args": args,
                "body": body,
                "namespace": ns_name,
                "scope": ns_scope
            }
            continue

        # Variable declarations (run immediately)
        if "var" in split_code:
            var_index = split_code.index("var")
            var_name = split_code[var_index + 1]
            if var_index + 2 < len(split_code) and split_code[var_index + 2] == "=":
                expr_tokens = split_code[var_index + 3:]
                value = evaluate_expression(expr_tokens)
            else:
                value = None
            variables[var_name] = {
                "scope": split_code[0] if in_namespace[0] else "global",
                "namespace": in_namespace[1],
                "value": value
            }
            i += 1
            continue

        # Skip non-declaration code inside namespaces
        if in_namespace[0]:
            i += 1
            continue

        # Function call without namespace
        if (
            split_code[0] in functions and
            len(split_code) >= 3 and
            split_code[1] == "(" and
            split_code[-1] == ")"
        ):
            func = functions[split_code[0]]
            if func["scope"] == "public" or func["namespace"] is None:
                args = split_code[2:-1]
                local_vars = dict(zip(func['args'], [evaluate_expression([arg]) for arg in args]))
                for func_line in func['body']:
                    parts = split_components([func_line])
                    if parts[0] == "print":
                        expr = parts[1:]
                        result = evaluate_expression(expr, local_vars)
                        print(result)
                    elif parts[0] == "sys" and parts[1] == "printLine":
                        expr = parts[3:-1]
                        result = evaluate_expression(expr, local_vars)
                        print(result)
            else:
                print(f"Error: Function {split_code[0]} is private, must call with namespace")
            i += 1
            continue

        if (
            len(split_code) >= 5 and
            split_code[1] == "." and
            split_code[3] == "(" and
            split_code[-1] == ")"
        ):
            namespace = split_code[0]
            func_name = split_code[2]
            args = split_code[4:-1]

            if namespace in pointers and func_name in functions:
                func = functions[func_name]
                if func["namespace"] == namespace:
                    local_vars = dict(zip(func['args'], [evaluate_expression([arg]) for arg in args]))
                    for func_line in func['body']:
                        parts = split_components([func_line])
                        if (
                            len(parts) >= 4 and
                            parts[0] == "sys" and
                            parts[1] == "printLine" and
                            parts[2] == "(" and
                            parts[-1] == ")"
                        ):
                            expr = parts[3:-1]
                            result = evaluate_expression(expr, local_vars)
                            print(result)
                    i += 1
                    continue
                else:
                    print(f"Error: Function {func_name} does not belong to namespace {namespace}")
            else:
                print(f"Error: Namespace or function not found: {namespace}.{func_name}")
            i += 1
            continue

        i += 1

interpret(code_lines)
