// ==================== CONFIG ====================
var CONFIG = {
  MODE: 'REPORT',          // REPORT | DELETE_NON_STARRED | DELETE_NON_IMPORTANT | DELETE_NON_STARRED_AND_NON_IMPORTANT | DELETE_ALL | DELETE_BY_TIME | DELETE_BY_SENDER
  TIME_THRESHOLD: '30d',   // Nd / Nm / Ny  ->  7d = week, 1d = day, 1y = year
  SENDER_LIST: [],         // e.g. ['classroom.google.com', 'noreply@somesite.com']
  DRY_RUN: true,           // always test with true first
  BATCH_SIZE: 100
};

function runCleanup() {
  switch (CONFIG.MODE) {
    case 'DELETE_NON_STARRED': return deleteNonStarred();
    case 'DELETE_NON_IMPORTANT': return deleteNonImportant();
    case 'DELETE_NON_STARRED_AND_NON_IMPORTANT': return deleteNonStarredAndNonImportant();
    case 'DELETE_ALL':           return deleteAll();
    case 'DELETE_BY_TIME':       return deleteByTime();
    case 'DELETE_BY_SENDER':     return deleteBySender();
    case 'REPORT':                return extractSenders();
    default: throw new Error('Unknown MODE: ' + CONFIG.MODE);
  }
}

// ---------- core deletion engine ----------
function trashByQuery(query) {
  var start = 0, total = 0;
  while (true) {
    var threads = GmailApp.search(query, start, CONFIG.BATCH_SIZE);
    if (threads.length === 0) break;

    Logger.log('Query "%s" -> %s threads (batch starting at %s)', query, threads.length, start);
    if (!CONFIG.DRY_RUN) {
      GmailApp.moveThreadsToTrash(threads);
    }
    total += threads.length;
    start += CONFIG.BATCH_SIZE;
    Utilities.sleep(1000); // stay under rate limits
  }
  Logger.log('Done. %s threads matched (dryRun=%s)', total, CONFIG.DRY_RUN);
  return total;
}

// ---------- feature 1: delete everything except starred/important (3 variants) ----------
function deleteNonStarred() {
  var query = '-is:starred -in:sent -in:drafts -in:trash -in:spam';
  return trashByQuery(query);
}

function deleteNonImportant() {
  var query = '-is:important -in:sent -in:drafts -in:trash -in:spam';
  return trashByQuery(query);
}

function deleteNonStarredAndNonImportant() {
  // deletes only if BOTH conditions are false - keeps anything starred OR important
  var query = '-is:starred -is:important -in:sent -in:drafts -in:trash -in:spam';
  return trashByQuery(query);
}

// ---------- feature 2: delete everything ----------
function deleteAll() {
  var query = '-in:sent -in:drafts -in:trash';
  return trashByQuery(query);
}

// ---------- feature 3: delete by age ----------
function deleteByTime() {
  var query = 'older_than:' + CONFIG.TIME_THRESHOLD + ' -in:trash -in:drafts';
  return trashByQuery(query);
}

// ---------- feature 4a: extract senders/domains + counts ----------
function extractSenders() {
  var counts = {};
  var start = 0;
  while (true) {
    var threads = GmailApp.search('-in:trash -in:spam', start, 200);
    if (threads.length === 0) break;
    threads.forEach(function (t) {
      t.getMessages().forEach(function (m) {
        var from = m.getFrom();
        var match = from.match(/@([\w.-]+)/);
        var key = match ? match[1] : from;
        counts[key] = (counts[key] || 0) + 1;
      });
    });
    start += 200;
  }
  var sorted = Object.keys(counts)
    .map(function (k) { return [k, counts[k]]; })
    .sort(function (a, b) { return b[1] - a[1]; });

  sorted.forEach(function (pair) { Logger.log('%s: %s', pair[0], pair[1]); });
  return sorted; // [[domain, count], ...] - inspect this before running DELETE_BY_SENDER
}

// ---------- feature 4b: delete by chosen sender/domain ----------
function deleteBySender() {
  if (!CONFIG.SENDER_LIST.length) throw new Error('SENDER_LIST is empty - populate it from extractSenders() output first');
  var total = 0;
  CONFIG.SENDER_LIST.forEach(function (sender) {
    total += trashByQuery('from:' + sender + ' -in:trash');
  });
  return total;
}

// ---------- optional: run automatically every night ----------
function createDailyTrigger() {
  ScriptApp.newTrigger('runCleanup').timeBased().everyDays(1).atHour(3).create();
}