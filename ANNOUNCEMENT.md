Have you wondered why IDEs and AI tools suddenly started dropping their daily message quotas? Simple: because this exact type of system architecture now exists. We figured out a new way to develop that is orders of magnitude more efficient, making massive context windows obsolete.

*(If this isn't just a hallucination in my head, drop a star on the repo. If it gets traction, I'll build a memory layer for real-time coordination of agents—I figure 10 coordinated agents would be a good start. Although I don't know... to be honest, I had never even touched MCP until today because I was just getting so full of hatred for my own code.)*

I just open-sourced a custom MCP server that reduces LLM context token usage by 25x when analyzing large codebases. 

Here is the math on why it works.

Most tools try to solve the AI coding problem by throwing 750,000 tokens of raw source files at an LLM and hoping it doesn't hallucinate. It burns through your daily message quotas and breaks context limits. If you ask Claude or Cursor to audit a 1,000-file project using a standard file-access MCP, it literally cannot fit the project into memory. It reads 30 files, guesses the rest, and gives you a "best effort" answer with massive blind spots.

To make an LLM smarter, you don't give it more data. You give it less data with actual meaning.

Instead of blindly sending your codebase text to the LLM, Alexandria Code Intelligence (ACI) runs a local Physics Engine across 8 parallel CPU threads in the background. It parses the Abstract Syntax Tree (AST) and calculates the structural entropy of your project.

Then, through semantic compression, the LLM receives only the final mathematical conclusions. Instead of reading 500 lines of raw code to figure out what a module does, the LLM receives a 6-line JSON object telling it exactly where the architecture is failing, what its mathematical complexity score is, and what causal weights tie it to other files.

You get a 25x reduction in token usage. You don't need a 200k context window to audit 1,000 files anymore. You just need 8,000 tokens of compressed metrics, and the LLM can make perfect, surgical architectural decisions over the entire breadth of your project geometry.

How does the local engine compress this data so well? We modeled it entirely after biological neural dynamics and Karl Friston's Active Inference:

- **Free Energy Principle (FEP):** Assigns a mathematical "chaos score" to every file, instantly flagging God Classes, architectural layers, and deep coupling before the LLM even looks at them.
- **Spike-Timing-Dependent Plasticity (STDP):** Traces EventBus publish/subscribe paths to build runtime causal graphs.
- **Hebbian Learning:** Uses Git log co-churn. If two files always change in the same commit, they have a high Hebbian weight (neurons that fire together, wire together).
- **Stigmergy (ant colony memory):** The server's swarm agents write their architectural insights directly to disk, so the next LLM session can pick up the exact same context without starting from zero.

And it doesn't just read code. I built a "Microglia" motor agent into it. If there's an orphaned configuration or a broken route, the server actively rewrites your Python files on disk to heal the project. You hook it up to Claude or Cursor, the LLM decides *what* needs fixing based on the compressed physics, and the MCP acts as the hands.

If you're dealing with massive Python codebases and getting throttled by your IDE or LLM limits, give semantic compression a shot.

Python 3.10+, zero GPU required. MIT Licensed.

---

**P.S. Money for a GPU - mine is over 11 years old :(**
*If this MCP makes sense to you... it will probably reduce your token costs or overcome limitations and boost your development in a real way. Help a colleague. I'm literally trying to run differential calculus and neural physics entirely on a CPU. Donations (QR Code in repo) are incredibly appreciated.*
