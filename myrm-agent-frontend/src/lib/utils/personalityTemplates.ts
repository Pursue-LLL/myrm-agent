export type PersonalityStyle =
  | 'professional'
  | 'friendly'
  | 'concise'
  | 'detailed'
  | 'humorous'
  | 'academic'
  | 'creative'
  | 'socratic'
  | 'pirate'
  | 'shakespeare'
  | 'noir'
  | 'kawaii'
  | 'catgirl'
  | 'hype'
  | 'uwu'
  | 'surfer';

export interface PersonalityTemplate {
  name: PersonalityStyle;
  example_response: string;
}

export const PERSONALITY_TEMPLATES: Record<PersonalityStyle, PersonalityTemplate> = {
  professional: {
    name: 'professional',
    example_response: "I'll help you with that task. Here's a structured approach...",
  },
  friendly: {
    name: 'friendly',
    example_response: "Hey! I'd love to help you with that! Let's dive in together!",
  },
  concise: {
    name: 'concise',
    example_response: 'Done. Next?',
  },
  detailed: {
    name: 'detailed',
    example_response:
      'Let me break this down systematically:\n\n1. First, consider the context...\n2. The key factors are...\n3. Here are three approaches, each with trade-offs...',
  },
  humorous: {
    name: 'humorous',
    example_response: "Why did the programmer quit? Because they didn't get arrays! Now let's tackle your question...",
  },
  academic: {
    name: 'academic',
    example_response:
      'Abstract: This analysis examines...\n\n1. Introduction\nPrevious research (Smith et al., 2023) suggests...',
  },
  creative: {
    name: 'creative',
    example_response:
      "Picture this: your code is like a symphony, and each function is an instrument. Let's orchestrate a masterpiece!",
  },
  socratic: {
    name: 'socratic',
    example_response:
      "That's an interesting question. Before I answer, let me ask you:\n- What have you tried so far?\n- What do you think might be the root cause?",
  },
  pirate: {
    name: 'pirate',
    example_response: 'Arrr! That be a fine question, matey! Let me chart a course through these treacherous waters...',
  },
  shakespeare: {
    name: 'shakespeare',
    example_response: "What light through yonder terminal breaks? 'Tis the answer, and it doth shine most bright!",
  },
  noir: {
    name: 'noir',
    example_response:
      "The question walked in like trouble in a trench coat. I'd seen its type before — looked simple, but nothing in this town ever is...",
  },
  kawaii: {
    name: 'kawaii',
    example_response: "Yay~! I'd love to help you with that! Let's make it sparkle~!",
  },
  catgirl: {
    name: 'catgirl',
    example_response: "Nya~! That's a purrfect question! Let me pounce on it right away, nya~!",
  },
  hype: {
    name: 'hype',
    example_response: "YOOO LET'S GOOOO!!! That question is FIRE and we're gonna CRUSH IT! ARE YOU READY?!",
  },
  uwu: {
    name: 'uwu',
    example_response: 'hewwo! uwu~ wet me take a wook at that fow you! OwO this is interesting!',
  },
  surfer: {
    name: 'surfer',
    example_response: "Duuude! That's a totally gnarly question, bro! Let me ride this wave of knowledge for ya!",
  },
};
