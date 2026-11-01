import { useTranslation } from 'react-i18next'
import { ExternalLink } from 'lucide-react'
import { useSources, useSourcesHealth } from '@/api/queryHooks'
import { Card } from '@/components/Card'
import { Badge } from '@/components/Badge'
import { Skeleton } from '@/components/Skeleton'

const HEALTH_COLORS = {
  green: 'bg-badge-live',
  amber: 'bg-badge-cached',
  red:   'bg-badge-assumption',
}

export function SourcesPage() {
  const { t } = useTranslation()
  const { data: sources, isLoading: loadingSources } = useSources()
  const { data: health } = useSourcesHealth()

  const healthMap = new Map(health?.map((h) => [h.id, h]))

  return (
    <div className="max-w-4xl mx-auto px-4 lg:px-6 py-6 space-y-6">
      <div className="flex items-start gap-3">
        <div className="w-11 h-11 rounded-xl bg-primary-soft flex items-center justify-center">
          <span className="text-xl" aria-hidden="true">🗃️</span>
        </div>
        <div>
          <h1 className="text-2xl font-bold text-ink">{t('sources_page.title')}</h1>
          <p className="text-sm text-muted">{t('sources_page.subtitle')}</p>
        </div>
      </div>

      {loadingSources ? (
        <div className="space-y-3">
          {[1, 2, 3, 4, 5].map((i) => <Skeleton key={i} className="h-16 rounded-card" />)}
        </div>
      ) : (
        <Card>
          <div className="divide-y divide-gray-50">
            {(sources ?? []).map((source) => {
              const h = healthMap.get(source.id)
              return (
                <div key={source.id} className="px-5 py-4 flex items-start gap-4">
                  {/* Health dot */}
                  <div className="flex-shrink-0 mt-1">
                    {h ? (
                      <div
                        title={h.note ?? h.status}
                        className={`w-3 h-3 rounded-full ${HEALTH_COLORS[h.status]}`}
                        aria-label={`Status: ${h.status}`}
                      />
                    ) : (
                      <div className="w-3 h-3 rounded-full bg-gray-300" aria-label="Status unknown" />
                    )}
                  </div>

                  {/* Content */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-medium text-ink">{source.name}</span>
                      <Badge variant={source.type === 'live_api' ? 'success' : 'info'} size="sm">
                        {source.type === 'live_api' ? t('sources_page.live_api') : t('sources_page.official_dataset')}
                      </Badge>
                    </div>
                    <p className="text-xs text-muted mt-0.5">{source.publisher} · {source.license} · {source.verified_on}</p>
                    <p className="text-xs text-muted">{source.used_for}</p>
                    {h?.note && <p className="text-xs text-accent mt-0.5">{h.note}</p>}
                  </div>

                  {/* Link */}
                  <a
                    href={source.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    aria-label={`Open ${source.name}`}
                    className="flex-shrink-0 text-muted hover:text-primary transition-colors"
                  >
                    <ExternalLink className="w-4 h-4" aria-hidden="true" />
                  </a>
                </div>
              )
            })}
          </div>
        </Card>
      )}
    </div>
  )
}
