<script>
  /** Where every dataset on this site comes from, what it is used for, and its terms. */
  let { publicBuild = false } = $props();

  const SOURCES = [
    {
      name: 'FEWS NET IPC classifications and livelihood zones',
      use: 'Observed IPC phase (current situation), ML1 and ML2 projections, and the livelihood-zone map.',
      terms: 'Famine Early Warning Systems Network (FEWS NET), fews.net. Cite FEWS NET as the source.',
    },
    {
      name: 'WFP market prices (VAM)',
      use: 'WFP market locations, and a staple-price index per market deflated with World Bank CPI.',
      terms: 'World Food Programme, via the Humanitarian Data Exchange (data.humdata.org). CC BY-IGO.',
    },
    {
      name: 'FAO GIEWS food prices',
      use: 'Where each FAO price series is located and which commodities it covers. No FAO price values are shown.',
      terms: 'FAO Global Information and Early Warning System (GIEWS) Food Price Monitoring and Analysis tool. Locations geocoded by this project with GeoNames.',
    },
    {
      name: 'Malaria Atlas Project global friction surfaces, 2019',
      use: 'Travel time by road and on foot, at 1 km, to cities of 50,000+ and to WFP markets, computed by this project.',
      terms: 'Weiss, D. J. et al. (2020), Nature Medicine 26, 1835–1838; malariaatlas.org. CC BY 4.0.',
    },
    {
      name: 'World Bank consumer price index',
      use: 'Deflating market prices to real terms. Prices after 2025 use the 2025 CPI.',
      terms: 'World Bank, World Development Indicators. CC BY 4.0.',
    },
    {
      name: 'GeoNames',
      use: 'Locating FAO market towns and cities of 50,000+.',
      terms: 'geonames.org. CC BY 4.0.',
    },
    {
      name: 'geoBoundaries administrative boundaries',
      use: 'Country, province or state and district outlines.',
      terms: 'Runfola, D. et al. (2020), geoBoundaries, PLOS ONE. CC BY 4.0.',
    },
    {
      name: 'Base map',
      use: 'Background map tiles and place labels.',
      terms: 'OpenFreeMap, OpenMapTiles and OpenStreetMap contributors (ODbL), credited on the map.',
    },
    {
      name: 'ACLED conflict data',
      use: publicBuild
        ? 'Used in this project\'s analysis but not published on this site, under ACLED\'s terms of use.'
        : 'Monthly national political-violence events and fatalities in the zone history panel.',
      terms: 'Armed Conflict Location & Event Data Project (ACLED), acleddata.com.',
    },
    {
      name: 'SMAP soil moisture and SMART trigger outputs',
      use: 'Counted in the coverage view only. Their values are not shown on this site.',
      terms: 'Provided to this project.',
    },
  ];
</script>

<section class="sources" aria-labelledby="sources-title">
  <h1 id="sources-title">Sources</h1>
  <p class="lede">
    An exploratory research tool for food-security early-warning data. It is not an official early-warning
    product and does not replace FEWS NET or IPC analyses. Travel times rank places well, but their absolute
    values are optimistic.
  </p>
  <dl>
    {#each SOURCES as s}
      <div class="item">
        <dt>{s.name}</dt>
        <dd>{s.use}</dd>
        <dd class="terms">{s.terms}</dd>
      </div>
    {/each}
  </dl>
</section>

<style>
  .sources { padding: 22px var(--pad) var(--pad); max-width: 820px; display: grid; gap: 14px; align-content: start; }
  h1 { font-size: var(--fs-title); line-height: 1.2; letter-spacing: -0.01em; }
  .lede { color: var(--muted); font-size: 14px; max-width: 70ch; }
  dl { margin: 6px 0 0; display: grid; background: var(--surface); border-radius: var(--radius-card); padding: 4px 20px; }
  .item { padding: 12px 0; border-top: 1px solid var(--rule); display: grid; gap: 3px; }
  .item:first-child { border-top: 0; }
  dt { font-weight: 600; font-size: 14px; }
  dd { margin: 0; }
  .terms { color: var(--muted); font-size: var(--fs-small); }
  @media (max-width: 760px) { .sources { padding: 16px; } }
</style>
