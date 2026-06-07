/**
 * useSupabaseQuery — Generic hook to query Supabase tables
 * with auto-refresh and realtime subscription support.
 */
import { useState, useEffect, useCallback } from 'react'
import { supabase, subscribeToTable } from '../lib/supabase'

/**
 * @param {string} table - Table name
 * @param {Object} opts
 * @param {string} opts.select - Columns (default '*')
 * @param {Array}  opts.filters - [{column, op, value}]
 * @param {string} opts.orderBy - Column to order by
 * @param {boolean} opts.ascending - Sort direction
 * @param {number} opts.limit - Row limit
 * @param {boolean} opts.realtime - Subscribe to changes
 * @param {number} opts.refreshInterval - Auto-refresh ms (0=off)
 */
export function useSupabaseQuery(table, opts = {}) {
  const {
    select = '*',
    filters = [],
    orderBy = null,
    ascending = false,
    limit = 100,
    realtime = false,
    refreshInterval = 0,
  } = opts

  const [data, setData] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const fetchData = useCallback(async () => {
    try {
      let query = supabase.from(table).select(select)
      for (const f of filters) {
        query = query[f.op || 'eq'](f.column, f.value)
      }
      if (orderBy) query = query.order(orderBy, { ascending })
      if (limit) query = query.limit(limit)

      const { data: rows, error: err } = await query
      if (err) throw err
      setData(rows || [])
      setError(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [table, select, JSON.stringify(filters), orderBy, ascending, limit])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  // Realtime subscription
  useEffect(() => {
    if (!realtime) return
    const unsub = subscribeToTable(table, '*', () => fetchData())
    return unsub
  }, [realtime, table, fetchData])

  // Auto-refresh
  useEffect(() => {
    if (!refreshInterval) return
    const id = setInterval(fetchData, refreshInterval)
    return () => clearInterval(id)
  }, [refreshInterval, fetchData])

  return { data, loading, error, refetch: fetchData }
}

/**
 * useConnectionStatus — Monitor Supabase connection
 */
export function useConnectionStatus() {
  const [status, setStatus] = useState('checking') // checking | online | offline
  const [lastChecked, setLastChecked] = useState(null)

  const check = useCallback(async () => {
    setStatus('checking')
    try {
      const { error } = await supabase.from('companies').select('symbol').limit(1)
      setStatus(error ? 'offline' : 'online')
    } catch {
      setStatus('offline')
    }
    setLastChecked(new Date())
  }, [])

  useEffect(() => {
    check()
    const id = setInterval(check, 60000) // Check every 60s
    return () => clearInterval(id)
  }, [check])

  return { status, lastChecked, recheck: check }
}
