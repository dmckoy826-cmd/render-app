export type Category = "laminate" | "pet" | "product_finish" | "other";

export interface Finish {
  id: number;
  name: string;
  category: Category;
  original_name: string;
  image_url: string;
  thumb_url: string;
  swatch_width_in: number;
  swatch_height_in: number;
  seamless: boolean;
  tags: string;
  created_at: string | null;
}

export interface BBox {
  min: [number, number, number];
  max: [number, number, number];
}

export interface Part {
  id: string;
  name: string;
  layer: string;
  block: string | null;
  requires_block_edit: boolean;
  bbox: BBox;
}

export interface LayerInfo {
  name: string;
  color: string;
  part_count: number;
}

export interface BlockInfo {
  name: string;
  instance_count: number;
  layers: string[];
  part_ids: string[];
}

export interface Structure {
  units: string;
  source_file?: string;
  analyzer?: string;
  extents: BBox;
  layers: LayerInfo[];
  blocks: BlockInfo[];
  parts: Part[];
}

export interface ModelSummary {
  id: number;
  name: string;
  original_name: string;
  status: "uploaded" | "analyzing" | "ready" | "failed";
  units: string;
  size_bytes: number;
  preview_url: string | null;
  layer_count: number;
  block_count: number;
  part_count: number;
  created_at: string | null;
}

export interface Assignment {
  id: number;
  target_kind: "layer" | "block" | "part";
  target_name: string;
  finish_id: number;
  scale_multiplier: number;
  finish: Finish | null;
}

export interface ModelDetail extends ModelSummary {
  structure: Structure | null;
  assignments: Assignment[];
  jobs: Job[];
}

export interface Suggestion {
  target_kind: "layer" | "block";
  target_name: string;
  finish_id: number;
  finish: Finish;
  score: number;
}

export interface Job {
  id: number;
  kind: "analyze" | "render";
  model_id: number;
  model_name: string;
  status: "queued" | "running" | "done" | "failed" | "canceled";
  progress: number;
  stage: string;
  runner: "mock" | "agent";
  settings: Record<string, any>;
  error: string;
  created_at: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface RenderResult {
  id: number;
  job_id: number;
  model_id: number;
  model_name: string;
  image_url: string;
  width: number;
  height: number;
  camera: string;
  quality: string;
  duration_s: number;
  finishes: { finish_id: number; name: string; category: Category; thumb: string; targets: string[] }[];
  created_at: string | null;
}

export interface PresetRule {
  match: "contains" | "starts_with" | "exact" | "regex";
  pattern: string;
  finish_id: number;
  target_kind: "layer" | "block" | "part";
  finish_name?: string;
  finish_thumb?: string;
}

export interface Preset {
  id: number;
  name: string;
  description: string;
  rules: PresetRule[];
  rule_count: number;
  created_at: string | null;
}

export interface SystemInfo {
  runner: string;
  engine_label: string;
  agent_connected: boolean;
  version: string;
  target: string;
}

export const CATEGORY_LABEL: Record<Category, string> = {
  laminate: "Laminate",
  pet: "PET",
  product_finish: "Product finish",
  other: "Other",
};

export const CATEGORY_COLOR: Record<Category, string> = {
  laminate: "bg-amber-500/15 text-amber-300 border-amber-500/30",
  pet: "bg-sky-500/15 text-sky-300 border-sky-500/30",
  product_finish: "bg-violet-500/15 text-violet-300 border-violet-500/30",
  other: "bg-zinc-500/15 text-zinc-300 border-zinc-500/30",
};
