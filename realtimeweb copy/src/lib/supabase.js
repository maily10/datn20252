/**
 * Supabase client + realtime helpers for the dashboard.
 */
import { createClient } from '@supabase/supabase-js'

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL
const supabaseKey = import.meta.env.VITE_SUPABASE_ANON_KEY

export const supabase = createClient(supabaseUrl, supabaseKey)

/**
 * Check Supabase connection health.
 */
export async function checkConnection() {
  try {
    const { error } = await supabase.from('companies').select('symbol').limit(1)
    if (error) return { ok: false, error: error.message }
    return { ok: true }
  } catch (err) {
    return { ok: false, error: err.message }
  }
}

/**
 * Subscribe to realtime changes on a table.
 * Returns an unsubscribe function.
 */
export function subscribeToTable(table, event, callback) {
  const channel = supabase
    .channel(`realtime-${table}-${Date.now()}`)
    .on('postgres_changes', { event, schema: 'public', table }, callback)
    .subscribe()

  return () => supabase.removeChannel(channel)
}
