// Mock responses for testing without backend
// TODO: Replace with actual FastAPI backend calls when available

const MOCK_RESPONSES: { match: RegExp; reply: string }[] = [
  {
    match: /\b(hi|hello|hey)\b/i,
    reply: 'Hello! I\'m QMeet, your intelligent AI assistant. I\'m ready to help with scheduling, questions, or anything else on your mind.',
  },
  {
    match: /meeting|schedule|calendar|book/i,
    reply: 'I can help with that. Based on the shared calendar, Thursday at 2:00 PM and Friday at 10:30 AM both look clear. I can send invites automatically once you confirm a time — which works best?',
  },
  {
    match: /weather|temperature|forecast/i,
    reply: 'Currently 19°C and partly cloudy at your location. The forecast shows clear skies by 3 PM — ideal if you were planning an outdoor session.',
  },
  {
    match: /who are you|what are you|your name/i,
    reply: 'I\'m QMeet — an embedded AI assistant designed for collaborative workspaces. I handle scheduling, answer questions, summarize notes, and connect to your team\'s tools.',
  },
  {
    match: /time|clock/i,
    reply: `The current time is ${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}.`,
  },
];

export function getMockResponse(input: string): string {
  const match = MOCK_RESPONSES.find((r) => r.match.test(input));
  return match?.reply ??
    'I\'m processing your request. In the live deployment, this response would come from the QMeet FastAPI backend via WebSocket. Feel free to ask about meetings, the weather, or who I am.';
}
