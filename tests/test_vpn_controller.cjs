const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const { test } = require('node:test');
const { runInNewContext } = require('node:vm');

const baseUrl = 'https://example.execute-api.ap-northeast-1.amazonaws.com/prod';
const configKey = 'vpn-controller-config';
const source = readFileSync(join(__dirname, '../web/vpn-controller.js'), 'utf8');

function button(action) {
    return {
        dataset: { action },
        addEventListener(type, callback) {
            assert.equal(type, 'click');
            this.click = callback;
        },
    };
}

function page({ admin = false, storage = new Map(), apiBase = baseUrl, promptedKey = 'test-key', storageBlocked = false, confirmStop = true } = {}) {
    const result = { dataset: {} };
    const registerResult = { dataset: {}, classList: new Set() };
    const publicKey = { value: '' };
    const reset = button();
    const register = button();
    const html = readFileSync(join(__dirname, '../web', admin ? 'admin.html' : 'index.html'), 'utf8');
    const actions = Object.fromEntries(Array.from(html.matchAll(/<button\b[^>]*\bdata-action="([^"]+)"[^>]*>/g), ([tag, action]) => {
        const actionButton = button(action);
        if (/\sdata-confirm-stop\b/.test(tag)) actionButton.dataset.confirmStop = '';
        return [action, actionButton];
    }));
    const prompts = [];
    const confirmations = [];
    const requests = [];
    const elements = {
        result,
        'reset-config': reset,
        ...(admin && { 'register-peer': register, 'register-result': registerResult, 'public-key': publicKey }),
    };
    const reply = { data: { state: 'stopped' }, code: 200, invalid: false };
    const access = (fn) => {
        if (storageBlocked) throw new Error('Storage disabled');
        return fn();
    };
    runInNewContext(source, {
        document: {
            currentScript: { dataset: { apiBase } },
            getElementById: (id) => elements[id] ?? null,
            querySelectorAll: () => Object.values(actions),
        },
        localStorage: {
            getItem: (key) => access(() => storage.get(key) ?? null),
            setItem: (key, value) => access(() => storage.set(key, value)),
            removeItem: (key) => access(() => storage.delete(key)),
        },
        window: {
            prompt: (text) => { prompts.push(text); return promptedKey; },
            confirm: (text) => { confirmations.push(text); return confirmStop; },
        },
        fetch: async (url, options) => {
            requests.push({ url, options });
            return {
                ok: reply.code < 400,
                status: reply.code,
                json: async () => {
                    if (reply.invalid) throw new SyntaxError('Not JSON');
                    return reply.data;
                },
            };
        },
    });
    return { result, reset, ...actions, register, publicKey, registerResult, prompts, confirmations, requests, reply };
}

test('both HTML templates load the shared script without an external script or an embedded key', () => {
    for (const file of ['index.html', 'admin.html']) {
        const html = readFileSync(join(__dirname, '../web', file), 'utf8');
        assert.deepEqual(html.match(/<script\b[^>]*>/g), [
            '<script defer src="vpn-controller.js" data-api-base="${api_base_url}">',
        ]);
    }
});

test('first use asks only for the API key and the admin page reuses it', async () => {
    const storage = new Map();
    const publicPage = page({ storage, promptedKey: ' test-key ' });
    publicPage.reply.data = { state: 'pending' };
    await publicPage.start.click();
    assert.deepEqual(publicPage.prompts, ['Enter your VPN API key']);
    const [{ url, options }] = publicPage.requests;
    assert.equal(url, `${baseUrl}/start`);
    assert.equal(options.headers['x-api-key'], 'test-key');
    assert.equal(options.method, 'POST');
    assert.deepEqual(JSON.parse(options.body), { action: 'start' });
    assert.equal(publicPage.result.dataset.state, 'working');

    const adminPage = page({ admin: true, storage });
    adminPage.reply.data = { state: 'stopping' };
    await adminPage.stop.click();
    assert.equal(adminPage.requests[0].url, `${baseUrl}/stop`);
    assert.deepEqual(JSON.parse(adminPage.requests[0].options.body), { action: 'stop' });
    assert.equal(adminPage.prompts.length, 0);
    assert.equal(adminPage.confirmations.length, 0);
    assert.equal(adminPage.requests[0].options.headers['x-api-key'], 'test-key');
    assert.equal(adminPage.result.dataset.state, 'working');
    adminPage.reset.click();
    assert.equal(storage.has(configKey), false);
    await publicPage.status.click();
    assert.equal(publicPage.prompts.length, 2);
});

test('normal page confirms a stop before sending the existing authenticated POST', async () => {
    const controller = page();
    controller.reply.data = { state: 'stopping' };
    await controller.stop.click();

    assert.equal(controller.confirmations.length, 1);
    assert.match(controller.confirmations[0], /disconnect all connected devices/);
    assert.equal(controller.requests.length, 1);
    const [{ url, options }] = controller.requests;
    assert.equal(url, `${baseUrl}/stop`);
    assert.equal(options.method, 'POST');
    assert.equal(options.headers['x-api-key'], 'test-key');
    assert.deepEqual(JSON.parse(options.body), { action: 'stop' });
    assert.equal(controller.result.dataset.state, 'working');
    assert.match(controller.result.textContent, /^Stopping the server/);

    controller.reply.data = { state: 'stopped' };
    await controller.status.click();
    assert.equal(controller.result.textContent, 'VPN not available');
});

test('cancelling stop on the normal page makes no request and does not ask for an API key', async () => {
    const controller = page({ confirmStop: false });
    await controller.stop.click();
    assert.equal(controller.confirmations.length, 1);
    assert.equal(controller.prompts.length, 0);
    assert.equal(controller.requests.length, 0);
});

test('reuses the previous deployment format only when the API URL matches', async () => {
    const storage = new Map([[configKey, JSON.stringify({ apiBase: `${baseUrl}/`, apiKey: 'existing-key', role: 'admin' })]]);
    const matched = page({ storage });
    await matched.status.click();
    assert.equal(matched.prompts.length, 0);
    assert.equal(matched.requests[0].options.headers['x-api-key'], 'existing-key');

    const changed = page({ storage, apiBase: 'https://new.example.com/prod' });
    await changed.status.click();
    assert.equal(changed.prompts.length, 1);
    assert.equal(changed.requests[0].url, 'https://new.example.com/prod/status');
    assert.equal(changed.requests[0].options.headers['x-api-key'], 'test-key');
});

test('both status panels classify the API state and health checks, not the message', async () => {
    for (const admin of [false, true]) {
        const controller = page({ admin });
        for (const [data, expected, text] of [
            [{ state: 'stopped' }, 'info', /^VPN not available$/],
            [{ state: 'stopping' }, 'working', /^VPN stopping/],
            [{ state: 'pending' }, 'working', /^VPN starting/],
            [{ state: 'running', statusChecksPassed: false }, 'working', /^VPN warming up/],
            [{ state: 'running', statusChecksPassed: true }, 'success', /^VPN available$/],
            [{ state: 'other', message: 'Available' }, 'info', /^Available$/],
        ]) {
            controller.reply.data = data;
            await controller.status.click();
            assert.equal(controller.result.dataset.state, expected);
            assert.match(controller.result.textContent, text);
        }
        assert.ok(controller.requests.every(({ options }) => options.method === 'GET' && options.body === undefined));
    }
});

test('missing key or unrendered HTML does not send an API request', async () => {
    const cancelled = page({ promptedKey: null });
    await cancelled.start.click();
    assert.equal(cancelled.result.dataset.state, 'error');
    assert.equal(cancelled.requests.length, 0);

    const unrendered = page({ apiBase: '${api_base_url}' });
    await unrendered.start.click();
    assert.equal(unrendered.result.dataset.state, 'error');
    assert.equal(unrendered.prompts.length, 0);
    assert.equal(unrendered.requests.length, 0);
});

test('admin registration preserves field validation, POST body and result handling', async () => {
    const adminPage = page({ admin: true });
    await adminPage.register.click();
    assert.equal(adminPage.registerResult.textContent, 'Public key is required.');
    assert.equal(adminPage.requests.length, 0);

    adminPage.publicKey.value = ' mock-peer ';
    adminPage.reply.code = 403;
    await adminPage.register.click();
    assert.equal(adminPage.registerResult.dataset.state, 'error');
    assert.match(adminPage.registerResult.textContent, /Forget saved API key/);
    assert.equal(adminPage.publicKey.value, ' mock-peer ');

    adminPage.reply.code = 200;
    adminPage.reply.data = { assignedIp: '192.0.2.10', publicKey: 'mock-peer', serverPublicKey: 'mock-server', presharedKey: 'mock-psk' };
    await adminPage.register.click();
    assert.equal(adminPage.requests[1].url, `${baseUrl}/register`);
    assert.deepEqual(JSON.parse(adminPage.requests[1].options.body), { publicKey: 'mock-peer' });
    assert.match(adminPage.registerResult.textContent, /192\.0\.2\.10\/32.*mock-psk/);
    assert.equal(adminPage.registerResult.dataset.state, 'success');
    assert.equal(adminPage.publicKey.value, '');
});

test('invalid gateway responses and blocked storage are handled', async () => {
    const controller = page({ storageBlocked: true });
    controller.reply.invalid = true;
    await controller.status.click();
    assert.equal(controller.result.dataset.state, 'error');
    assert.match(controller.result.textContent, /invalid response/);
    await controller.status.click();
    assert.equal(controller.requests.length, 2);
    assert.equal(controller.prompts.length, 1);
    controller.reset.click();
    await controller.status.click();
    assert.equal(controller.prompts.length, 2);
});
