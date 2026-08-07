import type { AnalyzeResponse, DemoSummary, HistoryEntry, RepositoryHealth } from "../types";

const BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export class ApiError extends Error {}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      // response wasn't JSON, keep statusText
    }
    throw new ApiError(detail);
  }
  return res.json() as Promise<T>;
}

export async function analyzePullRequest(prUrl: string): Promise<AnalyzeResponse> {
  const res = await fetch(`${BASE_URL}/api/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ pr_url: prUrl }),
  });
  return handleResponse<AnalyzeResponse>(res);
}

export async function fetchDemos(): Promise<DemoSummary[]> {
  const res = await fetch(`${BASE_URL}/api/demos`);
  return handleResponse<DemoSummary[]>(res);
}

export async function fetchDemo(id: string): Promise<AnalyzeResponse> {
  const res = await fetch(`${BASE_URL}/api/demos/${id}`);
  return handleResponse<AnalyzeResponse>(res);
}

export async function fetchHistory(params: { limit?: number; repository?: string } = {}): Promise<HistoryEntry[]> {
  const search = new URLSearchParams();
  if (params.limit) search.set("limit", String(params.limit));
  if (params.repository) search.set("repository", params.repository);
  const qs = search.toString();
  const res = await fetch(`${BASE_URL}/api/history${qs ? `?${qs}` : ""}`);
  return handleResponse<HistoryEntry[]>(res);
}

export async function fetchRepositoryHealth(params: { repository?: string; window?: number } = {}): Promise<RepositoryHealth> {
  const search = new URLSearchParams();
  if (params.repository) search.set("repository", params.repository);
  if (params.window) search.set("window", String(params.window));
  const qs = search.toString();
  const res = await fetch(`${BASE_URL}/api/repository-health${qs ? `?${qs}` : ""}`);
  return handleResponse<RepositoryHealth>(res);
}
