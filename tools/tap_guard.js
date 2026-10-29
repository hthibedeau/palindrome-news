// Tap guard (Hannah, Wed Oct 28, 2026: "I need the links to always go to the right page").
// Runs in every reader's browser, on every part of the page, including parts drawn later by the page's own code.
//  1. A link whose label names an outlet ("CBC News", "The Canadian Press via CP24", "Watch live on CTV News") must
//     open that outlet's site. If it doesn't, it is pointed at that outlet's own link in the same card; if the card has
//     none, it stops being a link, so a reader is never sent to the wrong newsroom.
//  2. Many cards are tappable everywhere (the headline link is stretched over the whole card). A label inside such a
//     card that names a DIFFERENT outlet (an outlet chip, a source line, a credit) would open the card's outlet.
//     The guard links that label to its own outlet's report in the card, or lifts it above the card link so a tap on
//     it does nothing rather than open the wrong outlet.
// tools/tap_check.py taps every outlet label on the page in a real browser after every automatic update and writes
// what it finds to live/taps.json. The master copy of this script is tools/tap_guard.js; tools/tap_check.py --install
// copies it into index.html between the PAL-TAP-GUARD markers.
(function tapGuard() {
  // Outlet name (as written on the page) -> its own sites. Wire services run on partner sites, so any site is fine.
  const WIRE = ['The Associated Press', 'Associated Press', 'AP', 'The Canadian Press', 'Canadian Press', 'CP', 'Reuters',
    'AFP', 'Agence France-Presse', 'Bloomberg', 'ANI', 'NTB', 'TASS', 'EFE', 'dpa', 'Xinhua', 'PA Media'];
  const POSTMEDIA = ['nationalpost.com', 'financialpost.com', 'torontosun.com', 'ottawacitizen.com', 'calgaryherald.com',
    'edmontonjournal.com', 'vancouversun.com', 'montrealgazette.com', 'theprovince.com', 'leaderpost.com', 'thestarphoenix.com',
    'windsorstar.com', 'lfpress.com', 'yahoo.com'];
  const SITES = {
    'CBC News': ['cbc.ca'], 'CBC': ['cbc.ca'], 'CBC Radio': ['cbc.ca'], 'CBC North': ['cbc.ca'], 'Radio-Canada': ['radio-canada.ca'],
    'CTV News': ['ctvnews.ca', 'bnnbloomberg.ca', 'cp24.com', 'iheartradio.ca'], 'CTV': ['ctvnews.ca', 'bnnbloomberg.ca', 'cp24.com'],
    'CP24': ['cp24.com', 'ctvnews.ca'], 'BNN Bloomberg': ['bnnbloomberg.ca'], 'Global News': ['globalnews.ca'],
    'CityNews': ['citynews.ca'], 'Noovo Info': ['noovo.info'], 'TVA Nouvelles': ['tvanouvelles.ca'], 'CPAC': ['cpac.ca'],
    'APTN News': ['aptnnews.ca'], 'CHCH': ['chch.com'], 'CHCH News': ['chch.com'], 'CHEK News': ['cheknews.ca'],
    'Toronto Star': ['thestar.com'], 'The Toronto Star': ['thestar.com'], 'The Globe and Mail': ['theglobeandmail.com'],
    'Globe and Mail': ['theglobeandmail.com'], 'National Post': POSTMEDIA, 'Financial Post': POSTMEDIA, 'Toronto Sun': POSTMEDIA,
    'Ottawa Citizen': POSTMEDIA, 'Calgary Herald': POSTMEDIA, 'Edmonton Journal': POSTMEDIA, 'Vancouver Sun': POSTMEDIA,
    'Montreal Gazette': POSTMEDIA, 'La Presse': ['lapresse.ca'], 'Le Devoir': ['ledevoir.com'], 'Le Soleil': ['lesoleil.com'],
    'The Hill Times': ['hilltimes.com'], 'The Hub': ['thehub.ca'], 'The Tyee': ['thetyee.ca'], 'National Observer': ['nationalobserver.com'],
    'Winnipeg Free Press': ['winnipegfreepress.com'], 'Times Colonist': ['timescolonist.com'], 'Cabin Radio': ['cabinradio.ca'],
    'Nunatsiaq News': ['nunatsiaq.com'], 'Yukon News': ['yukon-news.com'], 'NNSL': ['nnsl.com'], 'The Narwhal': ['thenarwhal.ca'],
    'Maclean’s': ['macleans.ca'], 'SaltWire': ['saltwire.com'], 'Daily Hive': ['dailyhive.com'], 'Castanet': ['castanet.net', 'castanetkamloops.net'],
    'Al Jazeera': ['aljazeera.com', 'aljazeera.net'], 'BBC News': ['bbc.com', 'bbc.co.uk'], 'BBC': ['bbc.com', 'bbc.co.uk'],
    'The Guardian': ['theguardian.com'], 'CNN': ['cnn.com'], 'CBS News': ['cbsnews.com'], 'NBC News': ['nbcnews.com'],
    'ABC News': ['abcnews.com', 'abcnews.go.com', 'abc.net.au'], 'NPR': ['npr.org'], 'PBS NewsHour': ['pbs.org'], 'PBS': ['pbs.org'],
    'Fox News': ['foxnews.com'], 'Fox Business': ['foxbusiness.com'], 'CNBC': ['cnbc.com'], 'MSNBC': ['msnbc.com'],
    'Politico': ['politico.com', 'politico.eu'], 'The Hill': ['thehill.com'], 'Axios': ['axios.com'],
    'The New York Times': ['nytimes.com'], 'New York Times': ['nytimes.com'], 'The Washington Post': ['washingtonpost.com'],
    'Washington Post': ['washingtonpost.com'], 'The Wall Street Journal': ['wsj.com'], 'Wall Street Journal': ['wsj.com'], 'WSJ': ['wsj.com'],
    'Newsweek': ['newsweek.com'], 'Time': ['time.com'], 'Sky News': ['news.sky.com', 'sky.com'], 'France 24': ['france24.com'],
    'DW News': ['dw.com'], 'Euronews': ['euronews.com'], 'Kyiv Independent': ['kyivindependent.com'], 'Kyiv Post': ['kyivpost.com'],
    'The Times of Israel': ['timesofisrael.com'], 'The Japan Times': ['japantimes.co.jp'], 'Middle East Eye': ['middleeasteye.net'],
  };
  const ANYWHERE = ['youtube.com', 'youtu.be']; // a network's own YouTube channel
  // A wire's own sites. A wire LINK may open a partner site that carries the wire story, but a wire label that is NOT a
  // link (an outlet chip, a source line) must never fall through to another outlet's own report.
  const WIRE_SITES = { 'The Associated Press': ['apnews.com'], 'Associated Press': ['apnews.com'], 'AP': ['apnews.com'],
    'The Canadian Press': ['thecanadianpress.com'], 'Canadian Press': ['thecanadianpress.com'], 'CP': ['thecanadianpress.com'],
    'Reuters': ['reuters.com'], 'AFP': ['afp.com'], 'Agence France-Presse': ['afp.com'], 'Bloomberg': ['bloomberg.com'], 'TASS': ['tass.com'] };
  const NAMES = Object.keys(SITES).concat(WIRE).sort((a, b) => b.length - a.length);
  const reEsc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const NAME_RE = new RegExp('(^|[^A-Za-z0-9])(' + NAMES.map(reEsc).join('|') + ')(?=$|[^A-Za-z0-9])', 'g');
  const LEAD = /^\s*(?:▶|►|&#9654;)?\s*(?:read (?:it )?(?:at|on)|watch(?: live)?(?: on| at)?|listen(?: on)?|live (?:updates|blog)(?: on| from)?|latest|first reported by|for subscribers:|via|on|from|the full report from|report from|video from|photos? from)?\s*/i;
  const FILLER = /\b(via|citing|and|the|report|reports|video|videos|photos?|live|on|youtube|blog|full|story|news|latest|update[sd]?|here|it|at|from|coverage|clip|watch|read|opens|·)\b|’s|'s|[()\/,·:–—&#\d↗▶►\-.]/gi;
  const host = (u) => { try { return new URL(u, location.href).hostname.replace(/^www\./, '').toLowerCase(); } catch (e) { return ''; } };
  const onSite = (h, list) => list.some((d) => h === d || h.endsWith('.' + d));
  const norm = (t) => (t || '').replace(/\s+/g, ' ').replace(/'/g, '’').trim();

  // The outlets a short label names, or null when the text is a headline or sentence rather than an outlet label.
  function outletsOf(text) {
    const t = norm(text); if (!t || t.length > 90) return null;
    const lead = t.replace(LEAD, '');
    const found = []; let m; NAME_RE.lastIndex = 0;
    while ((m = NAME_RE.exec(lead))) found.push({ name: m[2], at: m.index + m[1].length });
    if (!found.length || found[0].at > 1) return null;              // must start with the outlet's name
    let rest = lead; found.forEach((f) => { rest = rest.split(f.name).join(' '); });
    rest = rest.replace(/opens\s+\S+/i, ' ').replace(FILLER, ' ').trim();
    if (rest && rest.split(/\s+/).length > 2) return null;           // more than a short note: a headline, not a label
    return found.map((f) => f.name);
  }
  // Is this link the right page for this label? (null = the label names no outlet, nothing to judge)
  function labelOk(text, href) {
    const names = outletsOf(text); if (!names) return null;
    const h = host(href); if (!h || /^(mailto|tel|javascript):/i.test(href)) return null;
    if (/^#/.test(href || '') || h === location.hostname) return null; // a jump within the page
    const opens = /opens\s+([a-z0-9.-]+\.[a-z]{2,})/i.exec(norm(text));
    if (opens && !onSite(h, [opens[1].replace(/^www\./, '').toLowerCase()])) return false;
    if (names.some((n) => WIRE.includes(n))) return true;
    if (onSite(h, ANYWHERE)) return true;
    return names.some((n) => onSite(h, SITES[n] || []));
  }
  const okFor = (names, h) => names.some((n) => WIRE.includes(n)) || onSite(h, ANYWHERE) || names.some((n) => onSite(h, SITES[n] || []));
  const strictOk = (names, h) => onSite(h, ANYWHERE) || names.some((n) => onSite(h, (SITES[n] || []).concat(WIRE_SITES[n] || [])));
  // A link fit for a label: on the outlet's own site, or (for a wire) a link whose own label names that wire.
  const fits = (names, x) => strictOk(names, host(x.href)) || names.some((n) => WIRE.includes(n) && (outletsOf(x.textContent) || []).includes(n) && labelOk(x.textContent, x.getAttribute('href')));
  function findInCard(node, names) {
    for (let c = node.parentElement; c && c !== document.body; c = c.parentElement) {
      const a = [...c.querySelectorAll('a[href]')].find((x) => x !== node && !x.closest('.pal-notap') && /^https?:/i.test(x.href) && fits(names, x) && !x.dataset.palBad);
      if (a) return a;
      if (c.matches('section, .band, main')) break;
    }
    return null;
  }
  const report = { fixed: [], disabled: [], lifted: [], ran: 0 };
  let busy = false;
  function run() {
    busy = true; report.ran++;
    try {
      // 1. Links that name an outlet must open that outlet.
      document.querySelectorAll('a[href]').forEach((a) => {
        if (a.dataset.palChecked === a.href + '|' + a.textContent) return;
        if (a.getAttribute('aria-hidden') === 'true') return;           // a photo link that repeats the headline link
        const label = a.getAttribute('aria-label') && !a.textContent.trim() ? a.getAttribute('aria-label') : a.textContent;
        const ok = labelOk(label, a.getAttribute('href'));
        if (ok === false) {
          const names = outletsOf(label), good = findInCard(a, names);
          if (good) { report.fixed.push({ label: norm(label), was: a.href, now: good.href }); a.href = good.href; }
          else {
            report.disabled.push({ label: norm(label), href: a.href });
            const s = document.createElement('span'); s.className = (a.className + ' pal-notap').trim(); s.innerHTML = a.innerHTML;
            s.title = 'Link removed: it did not lead to ' + names[0]; a.replaceWith(s); return;
          }
        }
        a.dataset.palChecked = a.href + '|' + a.textContent;
      });
      // 2. Outlet labels that are not links, inside a card whose whole surface opens a link.
      const seen = new Set(), cards = new Map();
      document.querySelectorAll('a[href]').forEach((a) => {
        const s = getComputedStyle(a, '::after'); if (s.position !== 'absolute' || s.content === 'none' || s.content === 'normal') return;
        // the box the stretched link covers: its nearest positioned ancestor
        let c = a.parentElement; while (c && c !== document.body && getComputedStyle(c).position === 'static') c = c.parentElement;
        if (!c || c === document.body) return;
        if (!cards.has(c)) cards.set(c, []); cards.get(c).push(a);
      });
      cards.forEach((S, card) => {
        S = S.filter((x) => { const h = host(x.href); return h && h !== location.hostname; }); const cardHosts = S.map((x) => host(x.href)); if (!cardHosts.length) return;
        card.querySelectorAll('span, b, strong, small, em, i, cite, p, div, li').forEach((el) => {
          if (seen.has(el) || el.closest('a') || el.closest('.credit, figcaption, .ph, [data-credit]') || el.closest('.pal-notap') || el.children.length > 0 && [...el.children].some((k) => k.textContent.trim())) return;
          seen.add(el);
          const names = outletsOf(el.textContent); if (!names) return;
          if (S.every((x) => fits(names, x))) return;                 // a tap opens this same outlet: fine
          const good = findInCard(el, names);
          if (good && el.matches('span, b, strong, small, em, i, cite')) {
            const a = document.createElement('a'); a.href = good.href; a.target = '_blank'; a.rel = 'noopener';
            a.className = (el.className + ' pal-lift').trim(); a.innerHTML = el.innerHTML; el.replaceWith(a);
            report.fixed.push({ label: norm(a.textContent), was: '(card link) ' + cardHosts[0], now: good.href });
          } else { el.classList.add('pal-notap'); report.lifted.push({ label: norm(el.textContent), cardOpens: cardHosts[0] }); }
        });
      });
    } catch (e) { console.warn('tap guard', e); }
    busy = false;
  }
  const st = document.createElement('style');
  st.textContent = '.pal-notap, .pal-lift { position: relative; z-index: 4; } span.pal-notap, .pal-notap { cursor: default; } a.pal-lift { color: inherit; }';
  document.head.appendChild(st);
  let t = 0;
  const later = () => { if (busy) return; clearTimeout(t); t = setTimeout(run, 400); };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', run); else run();
  window.addEventListener('load', later);
  new MutationObserver(later).observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['href'] });
  window.PAL_tap = { outletsOf, labelOk, fits, run, report };
})();
