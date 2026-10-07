export const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export type Company = {
  id: string; name: string; description?: string | null; website?: string | null; linkedin_url?: string | null;
  location?: {country?: string; country_code?: string; city?: string; region?: string}; industry?: string[];
  employees?: {exact?: number; min?: number; max?: number}; funding?: {total_amount_usd?: number | null; last_funding_date?: string | null; rounds?: unknown[]};
  founded_year?: number | null; prospect_score?: number; prospect_category?: string; prospect_reason?: string[];
  potential_analytics_projects?: string[]; source_confidence?: number; sources?: {source_name:string;source_url:string;fields_provided:string[];collected_at:string}[];
  signals?: Record<string,number>; founders?: {name:string;role?:string}[]; demo?: boolean
}
export type Criteria = {query?:string;country_code?:string;industry?:string;employees_min?:number;employees_max?:number;funding_min?:number;funding_max?:number;founded_min?:number;founded_max?:number;score_min?:number;funded_within_months?:number;sort?:string;order?:string;page?:number;page_size?:number}

export async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, {cache:'no-store', headers:{'Content-Type':'application/json'}, ...options})
  if (!response.ok) { const body = await response.json().catch(() => ({})); throw new Error(body.detail || `${response.status} ${response.statusText}`) }
  return response.json()
}
export function money(value?: number | null) { return value == null ? 'Unavailable' : new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:1,notation:'compact'}).format(value) }
