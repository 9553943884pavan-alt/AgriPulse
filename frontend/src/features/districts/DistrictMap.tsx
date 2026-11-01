import { useState } from 'react'
import { CircleMarker, MapContainer, Popup, TileLayer } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import { useTranslation } from 'react-i18next'
import { useDistrictContext, useDistricts } from '@/api/queryHooks'
import { Card, CardHeader } from '@/components/Card'
import { SourceBadge } from '@/components/SourceBadge'

const STATUS_COLORS: Record<string, string> = {
  green: '#16a34a',
  amber: '#f59e0b',
  orange: '#f97316',
  red: '#dc2626',
  grey: '#6b7280',
}

export function DistrictMap() {
  const { t } = useTranslation()
  const districts = useDistricts()
  const [selectedDistrict, setSelectedDistrict] = useState<string | null>(null)
  const context = useDistrictContext(selectedDistrict)

  return (
    <Card>
      <div className="p-5">
        <CardHeader
          icon={<span aria-hidden="true">🗺️</span>}
          title={t('dashboard.district_map', 'Maharashtra district water context')}
        />
        {districts.isLoading ? (
          <p role="status" className="mt-4 text-sm text-muted">{t('misc.loading', 'Loading districts…')}</p>
        ) : districts.isError ? (
          <p role="alert" className="mt-4 text-sm text-danger">
            {t('errors.districts_failed', 'District data could not be loaded.')}
          </p>
        ) : (
          <>
            <p className="mt-2 text-xs text-muted">
              {t('dashboard.map_help', 'Select a district to see its groundwater, rainfall, reservoir, and irrigation data.')}
            </p>
            <div className="mt-4 h-[360px] overflow-hidden rounded-xl border border-gray-200">
              <MapContainer
                center={[19.2, 75.7]}
                zoom={6}
                minZoom={5}
                maxZoom={10}
                scrollWheelZoom
                className="h-full w-full"
                aria-label={t('dashboard.district_map', 'Maharashtra district water context')}
              >
                <TileLayer
                  attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
                  url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                />
                {districts.data?.map((district) => (
                  <CircleMarker
                    key={district.district}
                    center={[district.latitude, district.longitude]}
                    radius={selectedDistrict === district.district ? 9 : 7}
                    pathOptions={{
                      color: '#ffffff',
                      weight: 2,
                      fillColor: STATUS_COLORS[district.status_color] ?? STATUS_COLORS.grey,
                      fillOpacity: district.is_agricultural_district ? 0.9 : 0.45,
                    }}
                    eventHandlers={{
                      click: () => setSelectedDistrict(district.district),
                    }}
                  >
                    <Popup
                      eventHandlers={{
                        remove: () => setSelectedDistrict((current) =>
                          current === district.district ? null : current,
                        ),
                      }}
                    >
                      <div className="min-w-52 space-y-2 text-sm">
                        <strong>{district.names.en}</strong>
                        {selectedDistrict === district.district && context.isLoading && (
                          <p>{t('misc.loading', 'Loading…')}</p>
                        )}
                        {selectedDistrict === district.district && context.isError && (
                          <p role="alert" className="text-red-700">
                            {t('errors.district_context_failed', 'District context could not be loaded.')}
                          </p>
                        )}
                        {selectedDistrict === district.district && context.data && (
                          <>
                            <p>
                              {t('dashboard.groundwater', 'Groundwater')}: {String(context.data.groundwater.category.value)}
                              <SourceBadge sourced={context.data.groundwater.category} compact className="ml-1" />
                            </p>
                            <p>
                              {t('dashboard.extraction', 'Extraction')}: {context.data.groundwater.extraction_pct.value}%
                              <SourceBadge sourced={context.data.groundwater.extraction_pct} compact className="ml-1" />
                            </p>
                            {context.data.recent_rain.last_90d_mm && (
                              <p>
                                {t('dashboard.recent_rain', 'Rainfall (90 days)')}: {context.data.recent_rain.last_90d_mm.value} mm
                                <SourceBadge sourced={context.data.recent_rain.last_90d_mm} compact className="ml-1" />
                              </p>
                            )}
                            {context.data.reservoirs.map((reservoir) => (
                              <p key={reservoir.name}>
                                {reservoir.name}: {reservoir.live_storage_pct.value}%
                                <SourceBadge sourced={reservoir.live_storage_pct} compact className="ml-1" />
                              </p>
                            ))}
                          </>
                        )}
                      </div>
                    </Popup>
                  </CircleMarker>
                ))}
              </MapContainer>
            </div>
            <div className="mt-3 flex flex-wrap gap-3 text-xs text-muted" aria-label="Groundwater status legend">
              {[
                ['green', t('dashboard.gw_safe', 'Safe')],
                ['amber', t('dashboard.gw_semi_critical', 'Semi-critical')],
                ['red', t('dashboard.gw_critical', 'Critical / over-exploited')],
                ['grey', t('dashboard.gw_unavailable', 'Unavailable')],
              ].map(([color, label]) => (
                <span key={color} className="inline-flex items-center gap-1.5">
                  <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: STATUS_COLORS[color] }} />
                  {label}
                </span>
              ))}
            </div>
          </>
        )}
      </div>
    </Card>
  )
}
