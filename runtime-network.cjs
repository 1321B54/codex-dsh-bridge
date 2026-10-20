'use strict';
// Capture transport facts before the SDK flattens Error.cause. Never serialize
// errors, requests, headers, URLs, stacks, addresses or response bodies.
const channel = require('node:diagnostics_channel');
const {Agent, Dispatcher1Wrapper, setGlobalDispatcher} = require('undici');
// Use the already locked transport dependency. An ordinary Agent opens direct
// sockets; it never reads proxy environment variables or system/PAC settings.
const directAgent = new Agent({connect: {rejectUnauthorized: true}});
const directFetchDispatcher = new Dispatcher1Wrapper(directAgent);
setGlobalDispatcher(directAgent);
const PREFIX = 'DSH_NETWORK_FACTS ';
const CODES = new Set(['ECONNRESET', 'ECONNREFUSED', 'ENOTFOUND', 'EAI_AGAIN',
  'ETIMEDOUT', 'ENETUNREACH', 'EHOSTUNREACH', 'EPIPE', 'EPROTO',
  'UND_ERR_CONNECT_TIMEOUT', 'UND_ERR_HEADERS_TIMEOUT', 'UND_ERR_BODY_TIMEOUT',
  'UND_ERR_SOCKET', 'CERT_HAS_EXPIRED', 'ERR_TLS_CERT_ALTNAME_INVALID',
  'UNABLE_TO_VERIFY_LEAF_SIGNATURE', 'SELF_SIGNED_CERT_IN_CHAIN',
  'DEPTH_ZERO_SELF_SIGNED_CERT', 'UNABLE_TO_GET_ISSUER_CERT_LOCALLY']);

function errorCodes(error) {
  const seen = new Set(), codes = new Set(), pending = [error];
  while (pending.length && seen.size < 32) {
    const value = pending.shift();
    if (!value || typeof value !== 'object' || seen.has(value)) continue;
    seen.add(value);
    if (CODES.has(value.code)) codes.add(value.code);
    if (value.cause) pending.push(value.cause);
    if (Array.isArray(value.errors)) pending.push(...value.errors.slice(0, 16));
  }
  return [...codes].sort();
}

function relevant(value) {
  try {
    const host = new URL(value).hostname;
    return ['api.deepseek.com', '127.0.0.1', '[::1]', 'localhost'].includes(host);
  } catch { return false; }
}

function install() {
  const original = globalThis.fetch;
  const seen = new WeakSet();
  let count = 0;
  function report(error, phase) {
    if (!error || typeof error !== 'object' || seen.has(error) || count >= 16) return;
    seen.add(error);
    count++;
    process.stderr.write(PREFIX + JSON.stringify({codes: errorCodes(error), phase}) + '\n');
  }
  channel.channel('undici:request:error').subscribe(({request, error}) => {
    if (relevant(String(request?.origin))) report(error, 'transport');
  });
  globalThis.fetch = async function(input, options) {
    try { return await original.call(this, input, {...options, dispatcher: directFetchDispatcher}); }
    catch (error) {
      if (relevant(typeof input === 'string' || input instanceof URL ? input : input?.url)) {
        report(error, 'request');
      }
      throw error;
    }
  };
}

async function check(url, timeout = 8000) {
  if (!relevant(url)) throw new Error('Unreviewed network probe target');
  try {
    // No credential, body, model, files or automatic redirects. Any HTTP status
    // proves TLS/HTTP reachability only, never credential validity or balance.
    const response = await fetch(url.replace(/\/$/, '') + '/v1/messages', {
      method: 'HEAD', redirect: 'manual', signal: AbortSignal.timeout(timeout),
      dispatcher: directFetchDispatcher,
    });
    await response.body?.cancel();
    return {status: 'passed', http_status: response.status, error_codes: []};
  } catch (error) {
    return {status: 'failed', http_status: null, error_codes: errorCodes(error),
      timed_out: error?.name === 'TimeoutError' || error?.name === 'AbortError'};
  }
}

module.exports = {errorCodes, check, PREFIX};
if (require.main === module) {
  check(process.argv[2]).then(result => {
    process.stdout.write(JSON.stringify(result) + '\n');
    process.exitCode = result.status === 'passed' ? 0 : 2;
  }).catch(() => {
    process.stdout.write(JSON.stringify({status: 'failed', http_status: null,
      error_codes: [], probe_error: true}) + '\n');
    process.exitCode = 2;
  }).finally(() => directAgent.close());
} else { install(); }
