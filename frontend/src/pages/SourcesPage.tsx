import { useTranslation } from 'react-i18next'
import { ExternalLink } from 'lucide-react'
import { useSources, useSourcesHealth } from '@/api/queryHooks'
import { Card } from '@/components/Card'
import { Badge } from '@/components/Badge'
import { Skeleton } from '@/components/Skeleton'

const HEALTH_COLORS = {
  green: 'bg-badge-live',
  amber: 'bg-badge-cached',
  red: 'bg-badge-assumption',
} as const

const HEALTH_VARIANTS = {
  green: 'success',
  amber: 'warning',
  red: 'danger',
} as const

const MODE_VARIANTS = {
  live: 'success',
  cached: 'warning',
  historical: 'info',
  static: 'muted',
} as const

export function SourcesPage() {
  const { t } = useTranslation()
  const { data: sources, isLoading: loadingSources } = useSources()
  const { data: health } = useSourcesHealth()

  const healthMap = new Map(health?.map((item) => [item.id, item]))
  const categories = [...new Set((sources ?? []).map((source) => source.category))]
  const sourceGroups = categories.map((category) => ({
    category,
    sources: (sources ?? []).filter((source) => source.category === category),
  }))

  return (
    <main className="h-full overflow-y-auto overscroll-contain max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
      <header className="flex items-start gap-3">
        <div className="w-11 h-11 shrink-0 rounded-xl bg-primary-soft flex items-center justify-center" aria-hidden="true">
          <span className="text-xl">🗃️</span>
        </div>
        <div className="min-w-0">
          <h1 className="text-2xl font-bold text-ink">{t('sources_page.title')}</h1>
          <p className="text-sm text-muted">{t('sources_page.subtitle')}</p>
        </div>
      </header>

      {loadingSources ? (
        <div className="space-y-3" role="status" aria-label="Loading sources">
          {[1, 2, 3, 4, 5].map((i) => <Skeleton key={i} className="h-24 rounded-card" />)}
        </div>
      ) : sourceGroups.length === 0 ? (
        <Card className="p-5 text-sm text-muted">{t('sources_page.empty', 'No sources are available.')}</Card>
      ) : (
        <div className="space-y-5">
          {sourceGroups.map((group) => (
            <section key={group.category} aria-labelledby={`source-group-${group.category}`}>
              <h2 id={`source-group-${group.category}`} className="mb-2 text-sm font-semibold uppercase tracking-wide text-muted">
                {group.category} <span className="font-normal normal-case">({group.sources.length})</span>
              </h2>
              <Card as="ul" className="divide-y divide-gray-100">
                {group.sources.map((source) => {
                  const itemHealth = healthMap.get(source.id)
                  return (
                    <li key={source.id} className="px-4 sm:px-5 py-4">
                      <article className="flex items-start gap-3 sm:gap-4">
                        <div className="shrink-0 pt-1" aria-hidden="true">
                          <span className={`block w-3 h-3 rounded-full ${itemHealth ? HEALTH_COLORS[itemHealth.status] : 'bg-gray-300'}`} />
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex flex-wrap items-center gap-2">
                            <h3 className="font-medium text-ink break-words">{source.name}</h3>
                            <Badge variant={MODE_VARIANTS[source.mode]} size="sm">{source.mode}</Badge>
                            {itemHealth ? (
                              <Badge variant={HEALTH_VARIANTS[itemHealth.status]} size="sm">
                                <span className="sr-only">{t('sources_page.status')}: </span>{itemHealth.status}
                              </Badge>
                            ) : (
                              <Badge variant="muted" size="sm">{t('sources_page.status')}: unknown</Badge>
                            )}
                          </div>
                          <dl className="mt-2 grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-1 text-xs text-muted">
                            <div><dt className="inline font-medium">{t('sources_page.publisher')}: </dt><dd className="inline break-words">{source.publisher}</dd></div>
                            <div><dt className="inline font-medium">{t('sources_page.license')}: </dt><dd className="inline">{source.license}</dd></div>
                            <div><dt className="inline font-medium">Data period: </dt><dd className="inline">{source.as_of}</dd></div>
                            {itemHealth?.last_ok && <div><dt className="inline font-medium">Last reachable: </dt><dd className="inline">{new Date(itemHealth.last_ok).toLocaleString()}</dd></div>}
                            {itemHealth && itemHealth.latency_ms >= 0 && <div><dt className="inline font-medium">Latency: </dt><dd className="inline">{itemHealth.latency_ms} ms</dd></div>}
                          </dl>
                          <p className="mt-2 text-sm text-muted break-words"><span className="font-medium text-ink">Collection &amp; use: </span>{source.methodology}</p>
                          <p className="mt-1 text-sm text-muted break-words"><span className="font-medium text-ink">Used for: </span>{source.used_for}</p>
                          {itemHealth?.note && <p className="mt-1 text-sm text-accent break-words">{itemHealth.note}</p>}
                        </div>
                        <a
                          href={source.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          aria-label={`Open ${source.name} (opens in a new tab)`}
                          className="shrink-0 inline-flex min-h-11 min-w-11 items-center justify-center rounded-lg text-muted hover:text-primary focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
                        >
                          <ExternalLink className="w-4 h-4" aria-hidden="true" />
                        </a>
                      </article>
                    </li>
                  )
                })}
              </Card>
            </section>
          ))}
        </div>
      )}
    </main>
  )
}
