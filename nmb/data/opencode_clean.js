// NeedMoreBench's opencode plugin. Loaded only by the private opencode server NMB starts for itself,
// never by the person's own opencode. Before every model request it leaves exactly NMB's prompt: the system text and
// the user text NMB sent, no tools, no identity, environment or instruction text from opencode, no earlier messages.
//
// NMB sends each call as one user message: ENVELOPE followed by JSON {system, user, max_tokens}. A request without
// it (a title, a summary, anything opencode starts by itself) is stopped here, so nothing else leaves the machine.

const ENVELOPE = "NMB-ENVELOPE "

function textOf(message) {
  const c = message && message.content
  if (typeof c === "string") return c
  if (Array.isArray(c)) return c.filter((p) => p && p.type === "text").map((p) => p.text || "").join("")
  return ""
}

function clean(input) {
  const users = (input.messages || []).filter((m) => m && m.role === "user")
  const last = users[users.length - 1]
  const raw = textOf(last)
  if (!raw.startsWith(ENVELOPE)) throw new Error("NeedMoreBench: not an NMB request")
  const call = JSON.parse(raw.slice(ENVELOPE.length))
  const part = Array.isArray(last.content) ? last.content.find((p) => p && p.type === "text") : undefined
  last.content = part ? [{ ...part, text: call.user }] : call.user
  input.messages = [last]
  const first = (input.system || [])[0]
  input.system = [first ? { ...first, text: call.system } : { type: "text", text: call.system }]
  for (const k of Object.keys(input.tools || {})) delete input.tools[k]
  if (input.options && typeof call.max_tokens === "number") input.options.maxTokens = call.max_tokens
}

async function setup(context) {
  const registrations = []
  for (const name of ["context", "generate", "compaction"]) {
    registrations.push(await context.session.hook(name, async (input) => clean(input)))
  }
  return async () => {
    for (const r of registrations) await r.dispose()
  }
}

export default { id: "needmorebench.clean", setup }
