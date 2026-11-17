// Message content only. The dashboard keeps rendering the team's existing chat elements.
export function formatAIAnswer(response) {
  return response.mode + " · " + response.model + "\n" + response.answer
    + (response.evidence?.length ? "\nCheck the supporting calculations below: AI interpretation can still make mistakes." : "");
}

export function assistantMessages(overview, turns = [], pending = null) {
  const messages = [];
  if (overview.status !== "idle") {
    const loading = ["scheduled", "loading"].includes(overview.status);
    messages.push({role: "assistant", status: loading ? "pending" : overview.status === "error" ? "error" : null,
      content: loading ? "Preparing an automatic overview of the selected data…"
        : overview.status === "ready" ? "Automatic overview\n" + formatAIAnswer(overview.response)
        : "Automatic overview\n" + overview.error + "\nYou can still ask a question. Choose New conversation to retry the overview."});
  }
  for (const turn of [...turns, pending].filter(Boolean)) {
    // The automatic review never invents a user question.
    if (turn.question !== undefined) messages.push({role: "user", content: turn.question});
    messages.push({role: "assistant", content: turn.answer, status: turn.status});
  }
  return messages;
}
