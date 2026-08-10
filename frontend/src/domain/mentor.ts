/** Founder AI mentor types (T3.7). */

export type MentorCitationKind = 'finding' | 'task' | 'verdict' | 'profile';

export type MentorCitation = {
  kind: MentorCitationKind;
  ref: string;
};

export type MentorChatTurn = {
  role: 'user' | 'assistant';
  content: string;
};

export type MentorChatResult = {
  reply: string;
  citations: MentorCitation[];
};
