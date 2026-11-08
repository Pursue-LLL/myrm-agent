/**
 * Progressive Web Enhancer - delivered into every HTML document by enhancers/inject_route.py
 * Provides:
 * 1. Event Listener interception (Vanilla/Vue/jQuery)
 * 2. React Fiber DevTools hook interception
 * 3. SPA Routing/Network Activity interception, with requests numbered and the start of each user gesture marked
 */

(function() {
    if (window.__myrm_enhancer_initialized) return;
    window.__myrm_enhancer_initialized = true;

    // --- 1. React Fiber Hook ---
    window.__REACT_DEVTOOLS_GLOBAL_HOOK__ = window.__REACT_DEVTOOLS_GLOBAL_HOOK__ || {
        supportsFiber: true,
        inject: function(renderer) {
            window.__reactRenderer = renderer;
        },
        onCommitFiberRoot: function(rendererID, root) {
            window.__reactFiberRoot = root;
        },
        onCommitFiberUnmount: function() {}
    };

    // --- 2. Vanilla/Vue Event Listener Interception ---
    window.__myrm_interactive_elements = new WeakSet();
    const originalAddEventListener = EventTarget.prototype.addEventListener;
    EventTarget.prototype.addEventListener = function(type, listener, options) {
        if (['click', 'mousedown', 'pointerdown', 'keydown', 'change'].includes(type)) {
            if (this instanceof Element) {
                // Ignore structural tags like html, head, body, script, style
                const tag = this.tagName.toLowerCase();
                if (!['html', 'head', 'body', 'script', 'style'].includes(tag)) {
                    window.__myrm_interactive_elements.add(this);
                }
            }
        }
        return originalAddEventListener.call(this, type, listener, options);
    };

    // --- 3. SPA Stability Tracking ---
    // Tracked requests are numbered and kept in a set, so a waiter can tell the requests one user gesture started
    // from the ones already in flight (wait/_action_settle.py reads this state).
    window.__myrm_spa_state = {
        pending: new Set(),
        requestSeq: 0,
        lastRequestEnd: -Infinity,
        gestureSeq: 0,
        gestureTime: -Infinity,
        get inflightRequests() { return this.pending.size; },
        lastMutationTime: performance.now(),
        lastRouteTime: performance.now(),
        stable: false
    };

    // 3.1 Network Tracking (Fetch/XHR)
    function trackRequest() {
        const id = ++window.__myrm_spa_state.requestSeq;
        window.__myrm_spa_state.pending.add(id);
        window.__myrm_spa_state.stable = false;
        return id;
    }

    function untrackRequest(id) {
        window.__myrm_spa_state.pending.delete(id);
        window.__myrm_spa_state.lastRequestEnd = performance.now();
    }

    // Ignore common noise/heartbeat/analytics requests: beacons and long-lived channels never settle. Whole path
    // segments only, so /login, /logout and /tracking stay tracked.
    const NOISE_SEGMENT = /\/(ping|heartbeat|analytics|metrics|track|log|ws|socket(\.io)?)(\/|$)/i;
    function isNoise(url) {
        try {
            return NOISE_SEGMENT.test(new URL(url, location.href).pathname);
        } catch (e) {
            return false;
        }
    }

    const originalFetch = window.fetch;
    window.fetch = new Proxy(originalFetch, {
        apply: function(target, thisArg, argumentsList) {
            const url = argumentsList[0] instanceof Request ? argumentsList[0].url : String(argumentsList[0]);
            if (isNoise(url)) {
                return Reflect.apply(target, thisArg, argumentsList);
            }
            const id = trackRequest();
            return Reflect.apply(target, thisArg, argumentsList).finally(() => untrackRequest(id));
        }
    });

    const originalXHR = window.XMLHttpRequest.prototype.send;
    window.XMLHttpRequest.prototype.send = new Proxy(originalXHR, {
        apply: function(target, thisArg, argumentsList) {
            const id = trackRequest();
            thisArg.addEventListener('loadend', () => untrackRequest(id));
            return Reflect.apply(target, thisArg, argumentsList);
        }
    });

    // 3.2 Routing Interception
    const originalPushState = history.pushState;
    const originalReplaceState = history.replaceState;
    
    function notifyRouteChanged() {
        window.__myrm_spa_state.lastRouteTime = performance.now();
        window.__myrm_spa_state.stable = false;
    }

    history.pushState = new Proxy(originalPushState, {
        apply: function(target, thisArg, argumentsList) {
            notifyRouteChanged();
            return Reflect.apply(target, thisArg, argumentsList);
        }
    });
    history.replaceState = new Proxy(originalReplaceState, {
        apply: function(target, thisArg, argumentsList) {
            notifyRouteChanged();
            return Reflect.apply(target, thisArg, argumentsList);
        }
    });
    window.addEventListener('popstate', notifyRouteChanged);
    window.addEventListener('hashchange', notifyRouteChanged);

    // 3.3 Mutation Observer
    const mo = new MutationObserver(() => {
        window.__myrm_spa_state.lastMutationTime = performance.now();
        window.__myrm_spa_state.stable = false;
    });
    // Start observing when document body is available
    const startObserver = () => {
        if (document.body) {
            mo.observe(document.body, { childList: true, subtree: true, attributes: true, characterData: true });
        } else {
            setTimeout(startObserver, 50);
        }
    };
    startObserver();

    // 3.4 Stability Checker Loop
    setInterval(() => {
        const now = performance.now();
        const timeSinceMutation = now - window.__myrm_spa_state.lastMutationTime;
        const timeSinceRoute = now - window.__myrm_spa_state.lastRouteTime;
        
        if (window.__myrm_spa_state.inflightRequests === 0 && timeSinceMutation > 500 && timeSinceRoute > 500) {
            if (!window.__myrm_spa_state.stable) {
                window.__myrm_spa_state.stable = true;
                if (window.__myrm_spa_stable_resolve) {
                    window.__myrm_spa_stable_resolve();
                    window.__myrm_spa_stable_resolve = null;
                }
                if (window.myrmSpaStableNotify) {
                    window.myrmSpaStableNotify().catch(() => {});
                }
            }
        } else {
            window.__myrm_spa_state.stable = false;
        }
    }, 100);

    // 3.5 Gesture Marking
    // The input events of one user action arrive close together (a click is pointerdown..click, typing is a key per
    // character). The requests it causes are the ones numbered after the first event of the burst.
    const GESTURE_GAP_MS = 400;
    const markGesture = () => {
        const state = window.__myrm_spa_state;
        const now = performance.now();
        if (now - state.gestureTime > GESTURE_GAP_MS) {
            state.gestureSeq = state.requestSeq;
        }
        state.gestureTime = now;
    };
    ['pointerdown', 'keydown', 'input', 'change', 'click'].forEach((type) => {
        window.addEventListener(type, markGesture, { capture: true, passive: true });
    });

    // --- 4. The Enhancer Execution (Called before snapshot) ---
    window.__myrm_enhance_dom = function() {
        let enhancedCount = 0;

        // 4.1 React Fiber Enhancement
        function processFiber(fiber) {
            if (!fiber) return;
            
            if (fiber.memoizedProps && fiber.stateNode instanceof Element) {
                const props = fiber.memoizedProps;
                if (props.onClick || props.onChange || props.onKeyDown || props.onMouseDown || props.onPointerDown) {
                    const el = fiber.stateNode;
                    const tag = el.tagName.toLowerCase();
                    if (!['button', 'a', 'input', 'select', 'textarea'].includes(tag) && !el.hasAttribute('role')) {
                        el.setAttribute('role', 'button');
                        el.setAttribute('data-myrm-react-interactive', 'true');
                        enhancedCount++;
                    }
                }
            }
            
            if (fiber.child) processFiber(fiber.child);
            if (fiber.sibling) processFiber(fiber.sibling);
        }

        if (window.__reactFiberRoot && window.__reactFiberRoot.current) {
            processFiber(window.__reactFiberRoot.current);
        } else {
            // Try to find fiber on DOM as fallback
            const allEls = document.querySelectorAll('*');
            for (let i = 0; i < allEls.length; i++) {
                const el = allEls[i];
                const keys = Object.keys(el);
                const reactKey = keys.find(k => k.startsWith('__reactFiber$'));
                if (reactKey) {
                    processFiber(el[reactKey]);
                    break; // Once we find the root or a node, the recursive processFiber might cover its subtree.
                    // Actually, if it's just a node, we need to process it and its siblings/children.
                }
            }
        }

        // 4.2 Vanilla/Vue WeakSet Enhancement
        const allElements = document.querySelectorAll('*');
        for (let i = 0; i < allElements.length; i++) {
            const el = allElements[i];
            if (window.__myrm_interactive_elements.has(el)) {
                const tag = el.tagName.toLowerCase();
                if (!['button', 'a', 'input', 'select', 'textarea'].includes(tag) && !el.hasAttribute('role')) {
                    el.setAttribute('role', 'button');
                    el.setAttribute('data-myrm-event-interactive', 'true');
                    enhancedCount++;
                }
            }
            // Check Vue specific 
            if (el.__vue__ || (el.__vnode && el.__vnode.data && el.__vnode.data.on)) {
                const tag = el.tagName.toLowerCase();
                if (!['button', 'a', 'input', 'select', 'textarea'].includes(tag) && !el.hasAttribute('role')) {
                    el.setAttribute('role', 'button');
                    el.setAttribute('data-myrm-vue-interactive', 'true');
                    enhancedCount++;
                }
            }
        }

        return enhancedCount;
    };
})();
