// English phrases are translation keys; they are translated where they are rendered.
export const calendarAssistantPrompt =
  'Explain in more detail what is planned for {{date}}: why each action falls on that date, how to prepare and what could change it.';
export const calendarAssistantIntro = 'Ask about the actions and warnings planned for this day.';
export const calendarAssistantPlaceholder = 'Ask about this day…';
export const calendarAssistantSuggestions = [
  'What could delay these actions?',
  'What should I prepare beforehand?',
  'Is the weather suitable for this work?',
] as const;
