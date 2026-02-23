export interface Agent {
  id: string;
  name: string;
  icon: string;
  description: string;
  placeholder: string;
  scenarios: Scenario[];
}

export interface Scenario {
  id: string;
  name: string;
  prompt: string;
}

export interface Model {
  id: string;
  name: string;
}

export interface Message {
  role: "user" | "assistant";
  content: string;
}

export interface AppConfig {
  agents: Agent[];
  models: Model[];
  region: string;
}
