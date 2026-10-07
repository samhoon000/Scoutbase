export const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export type Company = {
  id: string; name: string; description?: string | null; website?: string | null; linkedin_url?: string | null;
  location?: {country?: string; country_code?: string; city?: string; region?: string}; industry?: string[];
  employees?: {exact?: number; min?: number; max?: number}; funding?: {total_amount_usd?: number | null; last_funding_date?: string | null; rounds?: unknown[]};
  founded_year?: number | null; prospect_score?: number; prospect_category?: string; prospect_reason?: string[];
  potential_analytics_projects?: string[]; source_confidence?: number; data_confidence?:number;
  sources?: {source_name:string;source_url:string;source_type?:string;fields_provided:string[];collected_at:string}[];
  field_evidence?:Record<string,{provider:string;url:string;collected_at:string;classification:string}>;
  field_conflicts?:{field:string;values:unknown[];sources:(string|null)[]}[];
  match_classification?:string;possible_matches?:string[];
  technology_signals?:{public_repos?:number;github_updated_at?:string};
  filing_signals?:{recent_filings?:{form:string;date:string}[];tickers?:string[]};
  signals?: Record<string,number>; founders?: {name:string;role?:string}[]
}
export type Criteria = {query?:string;country_code?:string;countries?:string[];region?:string;city?:string;industry?:string;industries?:string[];company_types?:string[];employees_min?:number;employees_max?:number;funding_min?:number;funding_max?:number;latest_round_min?:number;latest_round_max?:number;funding_stage?:string;founded_min?:number;founded_max?:number;score_min?:number;growth_score_min?:number;analytics_opportunity_min?:number;recently_founded_years?:number;active_company?:boolean;growing_headcount?:boolean;multiple_growth_signals?:boolean;high_transaction_volume?:boolean;large_customer_base?:boolean;multiple_products?:boolean;operational_data_heavy?:boolean;funded_within_months?:number;sort?:string;order?:string;page?:number;page_size?:number;force_refresh?:boolean}

export async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, {cache:'no-store', headers:{'Content-Type':'application/json'}, ...options})
  if (!response.ok) { const body = await response.json().catch(() => ({})); throw new Error(body.detail || `${response.status} ${response.statusText}`) }
  return response.json()
}
export function money(value?: number | null) { return value == null ? 'Unavailable' : new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:1,notation:'compact'}).format(value) }
