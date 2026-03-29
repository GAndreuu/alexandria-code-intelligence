# Configuring Your Development Standards

ACI adapts to **your** project's rules. You teach it what "good code" means by dropping a single YAML file in your project root.

---

## Quick Setup (30 seconds)

1. Copy `examples/contract.example.yaml` into your project:
   ```bash
   mkdir .aci
   cp contract.example.yaml your-project/.aci/contract.yaml
   ```

2. Edit the rules to match your team's standards.

3. That's it. ACI auto-discovers the file and enforces your rules.

---

## Where ACI Looks for Your Contract

ACI searches for configuration files in this order (first match wins):

| Priority | Path                    |
|----------|-------------------------|
| 1        | `.aci/contract.yaml`    |
| 2        | `.aci/contract.yml`     |
| 3        | `aci.yaml`              |
| 4        | `.aci.yaml`             |

If **no file is found**, ACI uses sensible defaults (300 LOC limit, require docstrings, forbid bare excepts, etc.).

---

## What You Can Configure

### Structural Limits
Control the physical size of your code units:

| Rule                  | Default | What it does                                    |
|-----------------------|---------|-------------------------------------------------|
| `max_loc_per_class`   | 300     | Flags "God Classes" above this line count       |
| `max_loc_per_file`    | 500     | Flags files that should be split                |
| `max_function_args`   | 6       | Flags functions with too many parameters        |

### Required Patterns
Enforce what every module **must** have:

| Rule                      | Default | What it does                                |
|---------------------------|---------|---------------------------------------------|
| `require_docstrings`      | true    | Every public class/function needs a docstring |
| `require_type_hints`      | false   | Enforce type annotations                     |
| `require_test_file`       | true    | Every module needs a `test_*.py`             |
| `require_logger`          | true    | Must use `logging`, not `print()`            |
| `require_config_dataclass`| false   | Require a `@dataclass` Config per module     |

### Forbidden Patterns
Ban dangerous code patterns:

| Rule                     | Default | What it does                                |
|--------------------------|---------|---------------------------------------------|
| `forbid_bare_except`     | true    | No `except:` without exception type         |
| `forbid_print_statements`| true    | No `print()` — use logger                   |
| `forbid_magic_numbers`   | true    | No unexplained numeric literals             |
| `forbid_fstring_logs`    | false   | No `logger.info(f"...")` — use % formatting |

### Architecture Layers
This is the most powerful feature. Define your project's layer hierarchy, and ACI will **automatically detect architectural violations** (e.g., your API layer importing directly from your database layer, skipping the service layer).

```yaml
layers:
  L1_data:
    - "db/"
    - "models/"
  L2_business:
    - "services/"
    - "domain/"
  L3_presentation:
    - "api/"
    - "cli/"
```

ACI will flag any file in `api/` that imports directly from `db/`.

### Custom Anti-Patterns
Define your own regex-based rules for project-specific conventions:

```yaml
custom:
  - pattern: "requests\\.get\\("
    message: "Use our internal HTTP client instead of raw requests"
    severity: "error"

  - pattern: "datetime\\.now\\("
    message: "Use utils.now() for testable time"
    severity: "warning"
```

---

## What Happens Without a Contract?

ACI still works perfectly. The Physics Engine (FEP, STDP, Hebbian), the Dependency Graph, the Swarm Agents, and the Dream cycle all run without any configuration. The contract only influences the **Critic Agent's scoring** and the **anti-pattern scanner**.

Think of it this way:
- **Without contract** → ACI is a universal physicist that measures your code's entropy
- **With contract** → ACI is a physicist + judge that knows your team's laws
