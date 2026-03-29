# Alexandria Code Intelligence (ACI) 🧠

**A Biologically-Inspired MCP Server for Autonomous Codebase Healing & Analysis.**

[![FastMCP](https://img.shields.io/badge/FastMCP-3.1.1-blue.svg)](https://gofastmcp.com)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

ACI is not a simple static linter. It is a persistent, multi-threaded **Physics Engine and Motor Cortex** for your codebase, designed to be plugged into any LLM (Claude, Cursor, Codex) via the Model Context Protocol (MCP).

By applying biological principles like **Active Inference**, **Spike-Timing-Dependent Plasticity (STDP)**, and **Microglial Phagocytosis**, ACI turns your AI assistant into a living meta-architect that predicts bugs, calculates codebase chaos, and autonomously heals your project.

---

## ⚡ Key Features

* **Code Physics Engine (FEP):** Calculates the Free Energy Principle (Chaos/Surprise) of any Python module, scoring `[-1.0, 1.0]` metric to detect God Classes before they break your system.
* **Hebbian Causal Wiring:** Discovers invisible coupling through Git Co-Churn and dynamically maps EventBus `publish/subscribe` networks (STDP tracking).
* **Immune System (Microglia Healer):** The engine doesn't just read code—it writes it. Capable of intercepting missing configuration injections, pruning dead routes, and automatically rewriting Technical Debt.
* **Swarm Intelligence:** Run `run_swarm("all")` to unleash 5 parallel agents (Architect, Critic, Dreamer, Explorer, Archaeologist) that produce instantaneous, consolidated architectural reports.
* **8-Core Multithreading:** Overcomes the standard Python GIL by mapping heavy AST (Abstract Syntax Tree) compilation and regex searching across 8 worker processes. Parses 1,000+ file projects in ~2 seconds.

---

## 🚀 Quickstart

### Prerequisites
* Python 3.10+
* An MCP Client (Claude Desktop, Cursor, or your custom implementation)

### Installation
Clone this repository and install it globally (so your MCP client can access it anywhere):

```bash
git clone https://github.com/YourName/alexandria-code-intelligence.git
cd alexandria-code-intelligence
pip install -e .
```

### Adding to your MCP Client Configuration

**For Claude Desktop (`claude_desktop_config.json`):**
```json
{
  "mcpServers": {
    "AlexandriaCodeIntelligence": {
      "command": "aci-server",
      "args": ["run"]
    }
  }
}
```

**For Cursor:**
1. Go to `Settings -> Features -> MCP`
2. Add a new Server.
3. Name: `AlexandriaCodeIntelligence`
4. Type: `command`
5. Command: `aci-server run`

---

## 🧠 How to Use It (Prompt Engineering)

Once hooked into your LLM, you are no longer constrained to manual grepping. You program via **Natural Language Commands**.

**Example Prompts for your AI:**

* **The Diagnostics:** *"Run the Physics Engine on `core/orchestrator.py`. What is the STDP causality footprint of this module? Who subscribes to its events?"*
* **The Healer (Motor Cortex):** *"I suspect I left some unmapped configurations. Wake up the Microglia and heal my ghost configs in `settings.py`."*
* **The Orchestrator:** *"Run the Dreamer swarm across the codebase to evaluate Observability (missing logs) and generate a dashboard."*

*(The AI will autonomously read the parameters, invoke the MCP functions recursively, and summarize the output for you).*

---

## ⚙️ Project Configuration (`.aci.yaml`)

ACI is completely universal. If you want its Immune System and EventBus mappers to understand *your* unique framework conventions, just drop an `.aci.yaml` in the root of your project:

```yaml
# .aci.yaml
event_bus:
  publish_pattern: "bus.emit"
  subscribe_pattern: "bus.on"
motor_cortex:
  config_map_file: "config/settings.py"
  router_file: "api/routes.py"
```

---

## ☕ Support the Project

**Money for a GPU - mine is over 11 years old :(**

If this MCP makes sense to you... it will probably reduce your API token costs, overcome IDE context limitations, and boost your development in a real way. Help a colleague out. I am literally trying to run differential calculus and neural physics entirely on a CPU. 

*Donations are incredibly appreciated. Check out the QR Code in this repository (Donation if you like.jpg).*
