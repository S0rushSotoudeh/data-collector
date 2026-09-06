// Run in the browser console on the authenticated /admin/gold-kalman page.
// Tests the actual shipped helpers without requests, DOM changes or new runs.
(() => {
  const source = Array.from(document.scripts, script => script.textContent)
    .find(text => text.includes('function gapData(rows,key)'));
  if (!source) throw Error('Open the Gold Kalman monitor first');
  const declarations = source.split('\n').filter(line =>
    ['const stamp=', 'const localTime=', 'function tehranInstant(',
     'function gapData(', 'function gapAreas('].some(prefix => line.startsWith(prefix))).join('\n');
  const helpers = new Function('windowStart', 'windowEnd', declarations +
    '\nreturn {localTime,tehranInstant,gapData,gapAreas};')(0, 602000);
  const assert = (condition, message) => { if (!condition) throw Error(message); };
  const instant = helpers.tehranInstant('2026-08-03T13:00:07');
  assert(instant === '2026-08-03T09:30:07.000Z', 'Tehran seconds must survive conversion');
  assert(helpers.localTime(instant) === '2026-08-03T13:00:07', 'Tehran round trip');
  assert(helpers.tehranInstant('2026-08-03T13:00') === '2026-08-03T09:30:00.000Z', 'Native minute-only input');
  const rows = [{decision_time: new Date(1000).toISOString(), z_score: 1},
                {decision_time: new Date(601000).toISOString(), z_score: 2}];
  const points = helpers.gapData(rows, 'z_score');
  assert(points.length === 4 && points[1][1] === null && points[2][1] === null,
    'Ten-minute scoring gap must break the line');
  assert(points[3][0] - points[0][0] === 600000, 'Gap must retain real elapsed time');
  const areas = helpers.gapAreas(rows);
  assert(areas.some(([a,b]) => a.xAxis === 2000 && b.xAxis === 601000),
    'Suppression gap must have a visible time interval');
  return {passed: 6, checks: 'Tehran seconds, minute input, ten-minute gap and suppression area'};
})()
