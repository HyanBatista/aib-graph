// Shapes returned by the AIB Graph server (see server/*/api.py).

export type Role = 'professor' | 'assistant' | 'student'
export type ClassStatus = 'draft' | 'indexing' | 'review' | 'building' | 'growing' | 'complete' | 'frozen'

export interface User {
  id: number
  email: string
  full_name: string
}

export interface Tokens {
  access: string
  refresh: string
}

export interface AuthResponse extends Tokens {
  user: User
}

export interface ClassInfo {
  id: number
  name: string
  status: ClassStatus
  status_detail: string
  language: string
  role: Role
  invite_code: string | null
  professor: string
  book_title: string | null
  topics_total: number
  topics_covered: number
  members: number
  frozen_at: string | null
}

export type MyState = 'new' | 'in_progress' | 'completed'

export interface GraphNode {
  id: number
  topic_id: number
  title: string
  level: number
  parent_topic_id: number | null
  ready: boolean
  created_at: string
  created_by_question_id: number | null
  created_by?: string | null
  avg_score?: number | null
  visits?: number
  my_state?: MyState
  my_score?: number | null
}

export interface GraphEdge {
  id: number
  src: number
  dst: number
  kind: 'growth' | 'link'
  origin_question_id: number | null
}

export type TopicState = 'covered' | 'available' | 'locked'

export interface UncoveredTopic {
  topic_id: number
  title: string
  level: number
  state: TopicState
}

export interface Graph {
  status: ClassStatus
  nodes: GraphNode[]
  edges: GraphEdge[]
  coverage: { covered: number; total: number }
  uncovered?: UncoveredTopic[]
}

export type QuestionOutcome = 'pending' | 'created_node' | 'linked_existing' | 'answered_only' | 'failed'

export interface Question {
  id: number
  node_id: number
  text: string
  answer_md: string
  outcome: QuestionOutcome
  resolved_topic_id: number | null
  target_node_id: number | null
  created_at: string
  student?: string
}

export interface QuizQuestion {
  prompt: string
  options: string[]
  answer_index?: number
  feedback?: string
}

export interface Progress {
  quiz_score: number | null
  quiz_answers: (number | null)[]
  question_done: boolean
  completed: boolean
}

export interface NodeDetail extends GraphNode {
  summary: string
  parent_title: string | null
  page_start: number
  page_end: number
  lesson_md: string
  quiz: QuizQuestion[]
  progress: Progress | null
  my_question: Question | null
  questions: Question[]
  can_ask: boolean
}

export interface QuizResult {
  score: number
  results: { correct: boolean; answer_index: number; feedback: string }[]
  progress: Progress
}

export interface IndexTopic {
  id: number
  parent_id: number | null
  level: number
  order: number
  title: string
  summary: string
  page_start: number
  page_end: number
  state: TopicState | null
  node_id: number | null
}

export interface BookIndex {
  book_title: string | null
  page_count: number
  topics: IndexTopic[]
  relations: { src: number; dst: number; kind: 'prerequisite' | 'related' }[]
}

export interface SubtopicIn {
  title: string
  summary: string
  page_start: number
  page_end: number
}

export interface TopicIn extends SubtopicIn {
  subtopics: SubtopicIn[]
}

export interface TestItem {
  id: number
  node_id: number
  node_title: string
  order: number
  kind: 'mcq' | 'open'
  prompt: string
  options: string[]
  points: number
  answer_index?: number | null
  rubric?: string
}

export interface ItemAnswer {
  id: number
  item_id: number
  choice: number | null
  text: string
  score: number | null
  feedback: string
  graded_by: string
}

export interface Attempt {
  id: number
  student_id: number
  student: string
  submitted_at: string | null
  score: number | null
  pending: number
  answers?: ItemAnswer[]
}

export interface Test {
  id: number
  title: string
  status: 'generating' | 'draft' | 'published' | 'closed'
  published_at: string | null
  items: TestItem[]
  covered_nodes: number
  total_nodes: number
  attempts?: Attempt[]
  my_attempt?: Attempt | null
}

export interface Member {
  user_id: number
  email: string
  full_name: string
  role: Role
}

export interface ClassMetrics {
  summary: {
    students: number
    nodes: number
    edges: number
    topics_total: number
    coverage: number
    avg_quiz: number | null
    completion_rate: number
    questions: number
  }
  question_outcomes: Record<string, number>
  growth: { date: string; nodes: number }[]
  per_node: {
    node_id: number
    title: string
    visits: number
    completions: number
    avg_score: number | null
    median_score: number | null
    questions: number
  }[]
  participation: {
    student_id: number
    name: string
    visited: number
    completed: number
    avg_score: number | null
    questions: number
    nodes_created: number
    test_score: number | null
  }[]
  mastery: { student_id: number; node_id: number; score: number }[]
  test: {
    status: string | null
    attempts: number
    avg_score: number | null
    median_score: number | null
    distribution: { bucket: string; count: number }[]
  }
}

export interface StudentMetrics {
  student: { id: number; name: string; email: string }
  summary: {
    nodes_total: number
    visited: number
    completed: number
    avg_score: number | null
    questions: number
    nodes_created: number
    test_score: number | null
  }
  per_node: {
    node_id: number
    title: string
    state: MyState
    quiz_score: number | null
    class_avg: number | null
    question_done: boolean
    mastery: number | null
  }[]
  questions: {
    id: number
    node_title: string
    text: string
    outcome: QuestionOutcome
    target_title: string | null
    created_at: string
  }[]
}

export interface ServerEvent {
  event: string
  payload: Record<string, unknown> & { class_id?: number }
}
