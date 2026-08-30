// node_modules/serwist/dist/chunks/waitUntil-BDu76Zx7.js
var _cacheNameDetails = {
  googleAnalytics: "googleAnalytics",
  precache: "precache-v2",
  prefix: "serwist",
  runtime: "runtime",
  suffix: typeof registration !== "undefined" ? registration.scope : ""
};
var _createCacheName = (cacheName) => {
  return [
    _cacheNameDetails.prefix,
    cacheName,
    _cacheNameDetails.suffix
  ].filter((value) => value && value.length > 0).join("-");
};
var eachCacheNameDetail = (fn) => {
  for (const key of Object.keys(_cacheNameDetails)) fn(key);
};
var cacheNames = {
  updateDetails: (details) => {
    eachCacheNameDetail((key) => {
      const detail = details[key];
      if (typeof detail === "string") _cacheNameDetails[key] = detail;
    });
  },
  getGoogleAnalyticsName: (userCacheName) => {
    return userCacheName || _createCacheName(_cacheNameDetails.googleAnalytics);
  },
  getPrecacheName: (userCacheName) => {
    return userCacheName || _createCacheName(_cacheNameDetails.precache);
  },
  getPrefix: () => {
    return _cacheNameDetails.prefix;
  },
  getRuntimeName: (userCacheName) => {
    return userCacheName || _createCacheName(_cacheNameDetails.runtime);
  },
  getSuffix: () => {
    return _cacheNameDetails.suffix;
  }
};
var supportStatus;
function canConstructResponseFromBodyStream() {
  if (supportStatus === void 0) {
    const testResponse = new Response("");
    if ("body" in testResponse) try {
      new Response(testResponse.body);
      supportStatus = true;
    } catch {
      supportStatus = false;
    }
    supportStatus = false;
  }
  return supportStatus;
}
var messages = {
  "invalid-value": ({ paramName, validValueDescription, value }) => {
    if (!paramName || !validValueDescription) throw new Error(`Unexpected input to 'invalid-value' error.`);
    return `The '${paramName}' parameter was given a value with an unexpected value. ${validValueDescription} Received a value of ${JSON.stringify(value)}.`;
  },
  "not-an-array": ({ moduleName, className, funcName, paramName }) => {
    if (!moduleName || !className || !funcName || !paramName) throw new Error(`Unexpected input to 'not-an-array' error.`);
    return `The parameter '${paramName}' passed into '${moduleName}.${className}.${funcName}()' must be an array.`;
  },
  "incorrect-type": ({ expectedType, paramName, moduleName, className, funcName }) => {
    if (!expectedType || !paramName || !moduleName || !funcName) throw new Error(`Unexpected input to 'incorrect-type' error.`);
    return `The parameter '${paramName}' passed into '${moduleName}.${className ? `${className}.` : ""}${funcName}()' must be of type ${expectedType}.`;
  },
  "incorrect-class": ({ expectedClassName, paramName, moduleName, className, funcName, isReturnValueProblem }) => {
    if (!expectedClassName || !moduleName || !funcName) throw new Error(`Unexpected input to 'incorrect-class' error.`);
    const classNameStr = className ? `${className}.` : "";
    if (isReturnValueProblem) return `The return value from '${moduleName}.${classNameStr}${funcName}()' must be an instance of class ${expectedClassName}.`;
    return `The parameter '${paramName}' passed into '${moduleName}.${classNameStr}${funcName}()' must be an instance of class ${expectedClassName}.`;
  },
  "missing-a-method": ({ expectedMethod, paramName, moduleName, className, funcName }) => {
    if (!expectedMethod || !paramName || !moduleName || !className || !funcName) throw new Error(`Unexpected input to 'missing-a-method' error.`);
    return `${moduleName}.${className}.${funcName}() expected the '${paramName}' parameter to expose a '${expectedMethod}' method.`;
  },
  "add-to-cache-list-unexpected-type": ({ entry }) => {
    return `An unexpected entry was passed to 'serwist.Serwist.addToPrecacheList()' The entry '${JSON.stringify(entry)}' isn't supported. You must supply an array of strings with one or more characters, objects with a url property or Request objects.`;
  },
  "add-to-cache-list-conflicting-entries": ({ firstEntry, secondEntry }) => {
    if (!firstEntry || !secondEntry) throw new Error("Unexpected input to 'add-to-cache-list-duplicate-entries' error.");
    return `Two of the entries passed to 'serwist.Serwist.addToPrecacheList()' had the URL ${firstEntry} but different revision details. Serwist is unable to cache and version the asset correctly. Please remove one of the entries.`;
  },
  "plugin-error-request-will-fetch": ({ thrownErrorMessage }) => {
    if (!thrownErrorMessage) throw new Error("Unexpected input to 'plugin-error-request-will-fetch', error.");
    return `An error was thrown by a plugin's 'requestWillFetch()' method. The thrown error message was: '${thrownErrorMessage}'.`;
  },
  "invalid-cache-name": ({ cacheNameId, value }) => {
    if (!cacheNameId) throw new Error(`Expected a 'cacheNameId' for error 'invalid-cache-name'`);
    return `You must provide a name containing at least one character for setCacheDetails({${cacheNameId}: '...'}). Received a value of '${JSON.stringify(value)}'`;
  },
  "unregister-route-but-not-found-with-method": ({ method }) => {
    if (!method) throw new Error("Unexpected input to 'unregister-route-but-not-found-with-method' error.");
    return `The route you're trying to unregister was not  previously registered for the method type '${method}'.`;
  },
  "unregister-route-route-not-registered": () => {
    return "The route you're trying to unregister was not previously registered.";
  },
  "queue-replay-failed": ({ name }) => {
    return `Replaying the background sync queue '${name}' failed.`;
  },
  "duplicate-queue-name": ({ name }) => {
    return `The queue name '${name}' is already being used. All instances of 'serwist.BackgroundSyncQueue' must be given unique names.`;
  },
  "expired-test-without-max-age": ({ methodName, paramName }) => {
    return `The '${methodName}()' method can only be used when the '${paramName}' is used in the constructor.`;
  },
  "unsupported-route-type": ({ moduleName, className, funcName, paramName }) => {
    return `The supplied '${paramName}' parameter was an unsupported type. Please check the docs for ${moduleName}.${className}.${funcName} for valid input types.`;
  },
  "not-array-of-class": ({ value, expectedClass, moduleName, className, funcName, paramName }) => {
    return `The supplied '${paramName}' parameter must be an array of '${expectedClass}' objects. Received '${JSON.stringify(value)},'. Please check the call to ${moduleName}.${className}.${funcName}() to fix the issue.`;
  },
  "max-entries-or-age-required": ({ moduleName, className, funcName }) => {
    return `You must define either 'config.maxEntries' or 'config.maxAgeSeconds' in '${moduleName}.${className}.${funcName}'`;
  },
  "statuses-or-headers-required": ({ moduleName, className, funcName }) => {
    return `You must define either 'config.statuses' or 'config.headers' in '${moduleName}.${className}.${funcName}'`;
  },
  "invalid-string": ({ moduleName, funcName, paramName }) => {
    if (!paramName || !moduleName || !funcName) throw new Error(`Unexpected input to 'invalid-string' error.`);
    return `When using strings, the '${paramName}' parameter must start with 'http' (for cross-origin matches) or '/' (for same-origin matches). Please see the docs for ${moduleName}.${funcName}() for more info.`;
  },
  "channel-name-required": () => {
    return "You must provide a channelName to construct a BroadcastCacheUpdate instance.";
  },
  "invalid-responses-are-same-args": () => {
    return "The arguments passed into responsesAreSame() appear to be invalid. Please ensure valid Responses are used.";
  },
  "expire-custom-caches-only": () => {
    return "You must provide a 'cacheName' property when using the expiration plugin with a runtime caching strategy.";
  },
  "unit-must-be-bytes": ({ normalizedRangeHeader }) => {
    if (!normalizedRangeHeader) throw new Error(`Unexpected input to 'unit-must-be-bytes' error.`);
    return `The 'unit' portion of the Range header must be set to 'bytes'. The Range header provided was "${normalizedRangeHeader}"`;
  },
  "single-range-only": ({ normalizedRangeHeader }) => {
    if (!normalizedRangeHeader) throw new Error(`Unexpected input to 'single-range-only' error.`);
    return `Multiple ranges are not supported. Please use a  single start value, and optional end value. The Range header provided was "${normalizedRangeHeader}"`;
  },
  "invalid-range-values": ({ normalizedRangeHeader }) => {
    if (!normalizedRangeHeader) throw new Error(`Unexpected input to 'invalid-range-values' error.`);
    return `The Range header is missing both start and end values. At least one of those values is needed. The Range header provided was "${normalizedRangeHeader}"`;
  },
  "no-range-header": () => {
    return "No Range header was found in the Request provided.";
  },
  "range-not-satisfiable": ({ size, start, end }) => {
    return `The start (${start}) and end (${end}) values in the Range are not satisfiable by the cached response, which is ${size} bytes.`;
  },
  "attempt-to-cache-non-get-request": ({ url, method }) => {
    return `Unable to cache '${url}' because it is a '${method}' request and only 'GET' requests can be cached.`;
  },
  "cache-put-with-no-response": ({ url }) => {
    return `There was an attempt to cache '${url}' but the response was not defined.`;
  },
  "no-response": ({ url, error }) => {
    let message = `The strategy could not generate a response for '${url}'.`;
    if (error) message += ` The underlying error is ${error}.`;
    return message;
  },
  "bad-precaching-response": ({ url, status }) => {
    return `The precaching request for '${url}' failed${status ? ` with an HTTP status of ${status}.` : "."}`;
  },
  "non-precached-url": ({ url }) => {
    return `'createHandlerBoundToURL("${url}")' was called, but that URL is not precached. Please pass in a URL that is precached instead.`;
  },
  "add-to-cache-list-conflicting-integrities": ({ url }) => {
    return `Two of the entries passed to 'serwist.Serwist.addToPrecacheList()' had the URL ${url} with different integrity values. Please remove one of them.`;
  },
  "missing-precache-entry": ({ cacheName, url }) => {
    return `Unable to find a precached response in ${cacheName} for ${url}.`;
  },
  "cross-origin-copy-response": ({ origin }) => {
    return `'@serwist/core.copyResponse()' can only be used with same-origin responses. It was passed a response with origin ${origin}.`;
  },
  "opaque-streams-source": ({ type }) => {
    const message = `One of the '@serwist/streams' sources resulted in an '${type}' response.`;
    if (type === "opaqueredirect") return `${message} Please do not use a navigation request that results in a redirect as a source.`;
    return `${message} Please ensure your sources are CORS-enabled.`;
  }
};
var generatorFunction = (code, details = {}) => {
  const message = messages[code];
  if (!message) throw new Error(`Unable to find message for code '${code}'.`);
  return message(details);
};
var messageGenerator = false ? fallback : generatorFunction;
var SerwistError = class extends Error {
  details;
  /**
  *
  * @param errorCode The error code that
  * identifies this particular error.
  * @param details Any relevant arguments
  * that will help developers identify issues should
  * be added as a key on the context object.
  */
  constructor(errorCode, details) {
    const message = messageGenerator(errorCode, details);
    super(message);
    this.name = errorCode;
    this.details = details;
  }
};
var isArray = (value, details) => {
  if (!Array.isArray(value)) throw new SerwistError("not-an-array", details);
};
var hasMethod = (object, expectedMethod, details) => {
  if (typeof object[expectedMethod] !== "function") {
    details.expectedMethod = expectedMethod;
    throw new SerwistError("missing-a-method", details);
  }
};
var isType = (object, expectedType, details) => {
  if (typeof object !== expectedType) {
    details.expectedType = expectedType;
    throw new SerwistError("incorrect-type", details);
  }
};
var isInstance = (object, expectedClass, details) => {
  if (!(object instanceof expectedClass)) {
    details.expectedClassName = expectedClass.name;
    throw new SerwistError("incorrect-class", details);
  }
};
var isOneOf = (value, validValues, details) => {
  if (!validValues.includes(value)) {
    details.validValueDescription = `Valid values are ${JSON.stringify(validValues)}.`;
    throw new SerwistError("invalid-value", details);
  }
};
var isArrayOfClass = (value, expectedClass, details) => {
  const error = new SerwistError("not-array-of-class", details);
  if (!Array.isArray(value)) throw error;
  for (const item of value) if (!(item instanceof expectedClass)) throw error;
};
var finalAssertExports = false ? null : {
  hasMethod,
  isArray,
  isInstance,
  isOneOf,
  isType,
  isArrayOfClass
};
var getFriendlyURL = (url) => {
  return new URL(String(url), location.href).href.replace(new RegExp(`^${location.origin}`), "");
};
var logger = typeof self === "undefined" ? null : (() => {
  if (!("__WB_DISABLE_DEV_LOGS" in globalThis)) self.__WB_DISABLE_DEV_LOGS = false;
  let inGroup = false;
  const methodToColorMap = {
    debug: "#7f8c8d",
    log: "#2ecc71",
    warn: "#f39c12",
    error: "#c0392b",
    groupCollapsed: "#3498db",
    groupEnd: null
  };
  const print = (method, args) => {
    if (self.__WB_DISABLE_DEV_LOGS) return;
    if (method === "groupCollapsed") {
      if (typeof navigator !== "undefined" && /^((?!chrome|android).)*safari/i.test(navigator.userAgent)) {
        console[method](...args);
        return;
      }
    }
    const styles = [
      `background: ${methodToColorMap[method]}`,
      "border-radius: 0.5em",
      "color: white",
      "font-weight: bold",
      "padding: 2px 0.5em"
    ];
    const logPrefix = inGroup ? [] : ["%cserwist", styles.join(";")];
    console[method](...logPrefix, ...args);
    if (method === "groupCollapsed") inGroup = true;
    if (method === "groupEnd") inGroup = false;
  };
  return Object.keys(methodToColorMap).reduce((api, method) => {
    api[method] = (...args) => {
      print(method, args);
    };
    return api;
  }, {});
})();
function timeout(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
var quotaErrorCallbacks = /* @__PURE__ */ new Set();
function stripParams(fullURL, ignoreParams) {
  const strippedURL = new URL(fullURL);
  for (const param of ignoreParams) strippedURL.searchParams.delete(param);
  return strippedURL.href;
}
async function cacheMatchIgnoreParams(cache, request, ignoreParams, matchOptions) {
  const strippedRequestURL = stripParams(request.url, ignoreParams);
  if (request.url === strippedRequestURL) return cache.match(request, matchOptions);
  const keysOptions = {
    ...matchOptions,
    ignoreSearch: true
  };
  const cacheKeys = await cache.keys(request, keysOptions);
  for (const cacheKey of cacheKeys) if (strippedRequestURL === stripParams(cacheKey.url, ignoreParams)) return cache.match(cacheKey, matchOptions);
}
var Deferred = class {
  promise;
  resolve;
  reject;
  /**
  * Creates a promise and exposes its resolve and reject functions as methods.
  */
  constructor() {
    this.promise = new Promise((resolve, reject) => {
      this.resolve = resolve;
      this.reject = reject;
    });
  }
};
var executeQuotaErrorCallbacks = async () => {
  if (true) logger.log(`About to run ${quotaErrorCallbacks.size} callbacks to clean up caches.`);
  for (const callback of quotaErrorCallbacks) {
    await callback();
    if (true) logger.log(callback, "is complete.");
  }
  if (true) logger.log("Finished running callbacks.");
};
var SUBSTRING_TO_FIND = "-precache-";
var deleteOutdatedCaches = async (currentPrecacheName, substringToFind = SUBSTRING_TO_FIND) => {
  const cacheNamesToDelete = (await self.caches.keys()).filter((cacheName) => {
    return cacheName.includes(substringToFind) && cacheName.includes(self.registration.scope) && cacheName !== currentPrecacheName;
  });
  await Promise.all(cacheNamesToDelete.map((cacheName) => self.caches.delete(cacheName)));
  return cacheNamesToDelete;
};
var cleanupOutdatedCaches = (cacheName) => {
  self.addEventListener("activate", (event) => {
    event.waitUntil(deleteOutdatedCaches(cacheNames.getPrecacheName(cacheName)).then((cachesDeleted) => {
      if (true) {
        if (cachesDeleted.length > 0) logger.log("The following out-of-date precaches were cleaned up automatically:", cachesDeleted);
      }
    }));
  });
};
var clientsClaim = () => {
  self.addEventListener("activate", () => self.clients.claim());
};
var waitUntil = (event, asyncFn) => {
  const returnPromise = asyncFn();
  event.waitUntil(returnPromise);
  return returnPromise;
};

// node_modules/idb/build/index.js
var instanceOfAny = (object, constructors) => constructors.some((c) => object instanceof c);
var idbProxyableTypes;
var cursorAdvanceMethods;
function getIdbProxyableTypes() {
  return idbProxyableTypes || (idbProxyableTypes = [
    IDBDatabase,
    IDBObjectStore,
    IDBIndex,
    IDBCursor,
    IDBTransaction
  ]);
}
function getCursorAdvanceMethods() {
  return cursorAdvanceMethods || (cursorAdvanceMethods = [
    IDBCursor.prototype.advance,
    IDBCursor.prototype.continue,
    IDBCursor.prototype.continuePrimaryKey
  ]);
}
var transactionDoneMap = /* @__PURE__ */ new WeakMap();
var transformCache = /* @__PURE__ */ new WeakMap();
var reverseTransformCache = /* @__PURE__ */ new WeakMap();
function promisifyRequest(request) {
  const promise = new Promise((resolve, reject) => {
    const unlisten = () => {
      request.removeEventListener("success", success);
      request.removeEventListener("error", error);
    };
    const success = () => {
      resolve(wrap(request.result));
      unlisten();
    };
    const error = () => {
      reject(request.error);
      unlisten();
    };
    request.addEventListener("success", success);
    request.addEventListener("error", error);
  });
  reverseTransformCache.set(promise, request);
  return promise;
}
function cacheDonePromiseForTransaction(tx) {
  if (transactionDoneMap.has(tx))
    return;
  const done = new Promise((resolve, reject) => {
    const unlisten = () => {
      tx.removeEventListener("complete", complete);
      tx.removeEventListener("error", error);
      tx.removeEventListener("abort", error);
    };
    const complete = () => {
      resolve();
      unlisten();
    };
    const error = () => {
      reject(tx.error || new DOMException("AbortError", "AbortError"));
      unlisten();
    };
    tx.addEventListener("complete", complete);
    tx.addEventListener("error", error);
    tx.addEventListener("abort", error);
  });
  transactionDoneMap.set(tx, done);
}
var idbProxyTraps = {
  get(target, prop, receiver) {
    if (target instanceof IDBTransaction) {
      if (prop === "done")
        return transactionDoneMap.get(target);
      if (prop === "store") {
        return receiver.objectStoreNames[1] ? void 0 : receiver.objectStore(receiver.objectStoreNames[0]);
      }
    }
    return wrap(target[prop]);
  },
  set(target, prop, value) {
    target[prop] = value;
    return true;
  },
  has(target, prop) {
    if (target instanceof IDBTransaction && (prop === "done" || prop === "store")) {
      return true;
    }
    return prop in target;
  }
};
function replaceTraps(callback) {
  idbProxyTraps = callback(idbProxyTraps);
}
function wrapFunction(func) {
  if (getCursorAdvanceMethods().includes(func)) {
    return function(...args) {
      func.apply(unwrap(this), args);
      return wrap(this.request);
    };
  }
  return function(...args) {
    return wrap(func.apply(unwrap(this), args));
  };
}
function transformCachableValue(value) {
  if (typeof value === "function")
    return wrapFunction(value);
  if (value instanceof IDBTransaction)
    cacheDonePromiseForTransaction(value);
  if (instanceOfAny(value, getIdbProxyableTypes()))
    return new Proxy(value, idbProxyTraps);
  return value;
}
function wrap(value) {
  if (value instanceof IDBRequest)
    return promisifyRequest(value);
  if (transformCache.has(value))
    return transformCache.get(value);
  const newValue = transformCachableValue(value);
  if (newValue !== value) {
    transformCache.set(value, newValue);
    reverseTransformCache.set(newValue, value);
  }
  return newValue;
}
var unwrap = (value) => reverseTransformCache.get(value);
function openDB(name, version, { blocked, upgrade, blocking, terminated } = {}) {
  const request = indexedDB.open(name, version);
  const openPromise = wrap(request);
  if (upgrade) {
    request.addEventListener("upgradeneeded", (event) => {
      upgrade(wrap(request.result), event.oldVersion, event.newVersion, wrap(request.transaction), event);
    });
  }
  if (blocked) {
    request.addEventListener("blocked", (event) => blocked(
      // Casting due to https://github.com/microsoft/TypeScript-DOM-lib-generator/pull/1405
      event.oldVersion,
      event.newVersion,
      event
    ));
  }
  openPromise.then((db) => {
    if (terminated)
      db.addEventListener("close", () => terminated());
    if (blocking) {
      db.addEventListener("versionchange", (event) => blocking(event.oldVersion, event.newVersion, event));
    }
  }).catch(() => {
  });
  return openPromise;
}
function deleteDB(name, { blocked } = {}) {
  const request = indexedDB.deleteDatabase(name);
  if (blocked) {
    request.addEventListener("blocked", (event) => blocked(
      // Casting due to https://github.com/microsoft/TypeScript-DOM-lib-generator/pull/1405
      event.oldVersion,
      event
    ));
  }
  return wrap(request).then(() => void 0);
}
var readMethods = ["get", "getKey", "getAll", "getAllKeys", "count"];
var writeMethods = ["put", "add", "delete", "clear"];
var cachedMethods = /* @__PURE__ */ new Map();
function getMethod(target, prop) {
  if (!(target instanceof IDBDatabase && !(prop in target) && typeof prop === "string")) {
    return;
  }
  if (cachedMethods.get(prop))
    return cachedMethods.get(prop);
  const targetFuncName = prop.replace(/FromIndex$/, "");
  const useIndex = prop !== targetFuncName;
  const isWrite = writeMethods.includes(targetFuncName);
  if (
    // Bail if the target doesn't exist on the target. Eg, getAll isn't in Edge.
    !(targetFuncName in (useIndex ? IDBIndex : IDBObjectStore).prototype) || !(isWrite || readMethods.includes(targetFuncName))
  ) {
    return;
  }
  const method = async function(storeName, ...args) {
    const tx = this.transaction(storeName, isWrite ? "readwrite" : "readonly");
    let target2 = tx.store;
    if (useIndex)
      target2 = target2.index(args.shift());
    return (await Promise.all([
      target2[targetFuncName](...args),
      isWrite && tx.done
    ]))[0];
  };
  cachedMethods.set(prop, method);
  return method;
}
replaceTraps((oldTraps) => ({
  ...oldTraps,
  get: (target, prop, receiver) => getMethod(target, prop) || oldTraps.get(target, prop, receiver),
  has: (target, prop) => !!getMethod(target, prop) || oldTraps.has(target, prop)
}));
var advanceMethodProps = ["continue", "continuePrimaryKey", "advance"];
var methodMap = {};
var advanceResults = /* @__PURE__ */ new WeakMap();
var ittrProxiedCursorToOriginalProxy = /* @__PURE__ */ new WeakMap();
var cursorIteratorTraps = {
  get(target, prop) {
    if (!advanceMethodProps.includes(prop))
      return target[prop];
    let cachedFunc = methodMap[prop];
    if (!cachedFunc) {
      cachedFunc = methodMap[prop] = function(...args) {
        advanceResults.set(this, ittrProxiedCursorToOriginalProxy.get(this)[prop](...args));
      };
    }
    return cachedFunc;
  }
};
async function* iterate(...args) {
  let cursor = this;
  if (!(cursor instanceof IDBCursor)) {
    cursor = await cursor.openCursor(...args);
  }
  if (!cursor)
    return;
  cursor = cursor;
  const proxiedCursor = new Proxy(cursor, cursorIteratorTraps);
  ittrProxiedCursorToOriginalProxy.set(proxiedCursor, cursor);
  reverseTransformCache.set(proxiedCursor, unwrap(cursor));
  while (cursor) {
    yield proxiedCursor;
    cursor = await (advanceResults.get(proxiedCursor) || cursor.continue());
    advanceResults.delete(proxiedCursor);
  }
}
function isIteratorProp(target, prop) {
  return prop === Symbol.asyncIterator && instanceOfAny(target, [IDBIndex, IDBObjectStore, IDBCursor]) || prop === "iterate" && instanceOfAny(target, [IDBIndex, IDBObjectStore]);
}
replaceTraps((oldTraps) => ({
  ...oldTraps,
  get(target, prop, receiver) {
    if (isIteratorProp(target, prop))
      return iterate;
    return oldTraps.get(target, prop, receiver);
  },
  has(target, prop) {
    return isIteratorProp(target, prop) || oldTraps.has(target, prop);
  }
}));

// node_modules/serwist/dist/chunks/printInstallDetails-ESDOoMBE.js
var copyResponse = async (response, modifier) => {
  let origin = null;
  if (response.url) origin = new URL(response.url).origin;
  if (origin !== self.location.origin) throw new SerwistError("cross-origin-copy-response", { origin });
  const clonedResponse = response.clone();
  const responseInit = {
    headers: new Headers(clonedResponse.headers),
    status: clonedResponse.status,
    statusText: clonedResponse.statusText
  };
  const modifiedResponseInit = modifier ? modifier(responseInit) : responseInit;
  const body = canConstructResponseFromBodyStream() ? clonedResponse.body : await clonedResponse.blob();
  return new Response(body, modifiedResponseInit);
};
var disableDevLogs = () => {
  self.__WB_DISABLE_DEV_LOGS = true;
};
var BACKGROUND_SYNC_DB_VERSION = 3;
var BACKGROUND_SYNC_DB_NAME = "serwist-background-sync";
var REQUEST_OBJECT_STORE_NAME = "requests";
var QUEUE_NAME_INDEX = "queueName";
var BackgroundSyncQueueDb = class {
  _db = null;
  /**
  * Add QueueStoreEntry to underlying db.
  *
  * @param entry
  */
  async addEntry(entry) {
    const tx = (await this.getDb()).transaction(REQUEST_OBJECT_STORE_NAME, "readwrite", { durability: "relaxed" });
    await tx.store.add(entry);
    await tx.done;
  }
  /**
  * Returns the first entry id in the ObjectStore.
  *
  * @returns
  */
  async getFirstEntryId() {
    return (await (await this.getDb()).transaction(REQUEST_OBJECT_STORE_NAME).store.openCursor())?.value.id;
  }
  /**
  * Get all the entries filtered by index
  *
  * @param queueName
  * @returns
  */
  async getAllEntriesByQueueName(queueName) {
    const results = await (await this.getDb()).getAllFromIndex(REQUEST_OBJECT_STORE_NAME, QUEUE_NAME_INDEX, IDBKeyRange.only(queueName));
    return results ? results : [];
  }
  /**
  * Returns the number of entries filtered by index
  *
  * @param queueName
  * @returns
  */
  async getEntryCountByQueueName(queueName) {
    return (await this.getDb()).countFromIndex(REQUEST_OBJECT_STORE_NAME, QUEUE_NAME_INDEX, IDBKeyRange.only(queueName));
  }
  /**
  * Deletes a single entry by id.
  *
  * @param id the id of the entry to be deleted
  */
  async deleteEntry(id) {
    await (await this.getDb()).delete(REQUEST_OBJECT_STORE_NAME, id);
  }
  /**
  *
  * @param queueName
  * @returns
  */
  async getFirstEntryByQueueName(queueName) {
    return await this.getEndEntryFromIndex(IDBKeyRange.only(queueName), "next");
  }
  /**
  *
  * @param queueName
  * @returns
  */
  async getLastEntryByQueueName(queueName) {
    return await this.getEndEntryFromIndex(IDBKeyRange.only(queueName), "prev");
  }
  /**
  * Returns either the first or the last entries, depending on direction.
  * Filtered by index.
  *
  * @param direction
  * @param query
  * @returns
  * @private
  */
  async getEndEntryFromIndex(query, direction) {
    return (await (await this.getDb()).transaction(REQUEST_OBJECT_STORE_NAME).store.index(QUEUE_NAME_INDEX).openCursor(query, direction))?.value;
  }
  /**
  * Returns an open connection to the database.
  *
  * @private
  */
  async getDb() {
    if (!this._db) this._db = await openDB(BACKGROUND_SYNC_DB_NAME, BACKGROUND_SYNC_DB_VERSION, { upgrade: this._upgradeDb });
    return this._db;
  }
  /**
  * Upgrades QueueDB
  *
  * @param db
  * @param oldVersion
  * @private
  */
  _upgradeDb(db, oldVersion) {
    if (oldVersion > 0 && oldVersion < BACKGROUND_SYNC_DB_VERSION) {
      if (db.objectStoreNames.contains(REQUEST_OBJECT_STORE_NAME)) db.deleteObjectStore(REQUEST_OBJECT_STORE_NAME);
    }
    db.createObjectStore(REQUEST_OBJECT_STORE_NAME, {
      autoIncrement: true,
      keyPath: "id"
    }).createIndex(QUEUE_NAME_INDEX, QUEUE_NAME_INDEX, { unique: false });
  }
};
var BackgroundSyncQueueStore = class {
  _queueName;
  _queueDb;
  /**
  * Associates this instance with a Queue instance, so entries added can be
  * identified by their queue name.
  *
  * @param queueName
  */
  constructor(queueName) {
    this._queueName = queueName;
    this._queueDb = new BackgroundSyncQueueDb();
  }
  /**
  * Append an entry last in the queue.
  *
  * @param entry
  */
  async pushEntry(entry) {
    if (true) {
      finalAssertExports.isType(entry, "object", {
        moduleName: "serwist",
        className: "BackgroundSyncQueueStore",
        funcName: "pushEntry",
        paramName: "entry"
      });
      finalAssertExports.isType(entry.requestData, "object", {
        moduleName: "serwist",
        className: "BackgroundSyncQueueStore",
        funcName: "pushEntry",
        paramName: "entry.requestData"
      });
    }
    delete entry.id;
    entry.queueName = this._queueName;
    await this._queueDb.addEntry(entry);
  }
  /**
  * Prepend an entry first in the queue.
  *
  * @param entry
  */
  async unshiftEntry(entry) {
    if (true) {
      finalAssertExports.isType(entry, "object", {
        moduleName: "serwist",
        className: "BackgroundSyncQueueStore",
        funcName: "unshiftEntry",
        paramName: "entry"
      });
      finalAssertExports.isType(entry.requestData, "object", {
        moduleName: "serwist",
        className: "BackgroundSyncQueueStore",
        funcName: "unshiftEntry",
        paramName: "entry.requestData"
      });
    }
    const firstId = await this._queueDb.getFirstEntryId();
    if (firstId) entry.id = firstId - 1;
    else delete entry.id;
    entry.queueName = this._queueName;
    await this._queueDb.addEntry(entry);
  }
  /**
  * Removes and returns the last entry in the queue matching the `queueName`.
  *
  * @returns
  */
  async popEntry() {
    return this._removeEntry(await this._queueDb.getLastEntryByQueueName(this._queueName));
  }
  /**
  * Removes and returns the first entry in the queue matching the `queueName`.
  *
  * @returns
  */
  async shiftEntry() {
    return this._removeEntry(await this._queueDb.getFirstEntryByQueueName(this._queueName));
  }
  /**
  * Returns all entries in the store matching the `queueName`.
  *
  * @returns
  */
  async getAll() {
    return await this._queueDb.getAllEntriesByQueueName(this._queueName);
  }
  /**
  * Returns the number of entries in the store matching the `queueName`.
  *
  * @returns
  */
  async size() {
    return await this._queueDb.getEntryCountByQueueName(this._queueName);
  }
  /**
  * Deletes the entry for the given ID.
  *
  * WARNING: this method does not ensure the deleted entry belongs to this
  * queue (i.e. matches the `queueName`). But this limitation is acceptable
  * as this class is not publicly exposed. An additional check would make
  * this method slower than it needs to be.
  *
  * @param id
  */
  async deleteEntry(id) {
    await this._queueDb.deleteEntry(id);
  }
  /**
  * Removes and returns the first or last entry in the queue (based on the
  * `direction` argument) matching the `queueName`.
  *
  * @returns
  * @private
  */
  async _removeEntry(entry) {
    if (entry) await this.deleteEntry(entry.id);
    return entry;
  }
};
var serializableProperties = [
  "method",
  "referrer",
  "referrerPolicy",
  "mode",
  "credentials",
  "cache",
  "redirect",
  "integrity",
  "keepalive"
];
var StorableRequest = class StorableRequest2 {
  _requestData;
  /**
  * Converts a Request object to a plain object that can be structured
  * cloned or stringified to JSON.
  *
  * @param request
  * @returns
  */
  static async fromRequest(request) {
    const requestData = {
      url: request.url,
      headers: {}
    };
    if (request.method !== "GET") requestData.body = await request.clone().arrayBuffer();
    request.headers.forEach((value, key) => {
      requestData.headers[key] = value;
    });
    for (const prop of serializableProperties) if (request[prop] !== void 0) requestData[prop] = request[prop];
    return new StorableRequest2(requestData);
  }
  /**
  * Accepts an object of request data that can be used to construct a
  * `Request` object but can also be stored in IndexedDB.
  *
  * @param requestData An object of request data that includes the `url` plus any relevant property of
  * [`requestInit`](https://fetch.spec.whatwg.org/#requestinit).
  */
  constructor(requestData) {
    if (true) {
      finalAssertExports.isType(requestData, "object", {
        moduleName: "serwist",
        className: "StorableRequest",
        funcName: "constructor",
        paramName: "requestData"
      });
      finalAssertExports.isType(requestData.url, "string", {
        moduleName: "serwist",
        className: "StorableRequest",
        funcName: "constructor",
        paramName: "requestData.url"
      });
    }
    if (requestData.mode === "navigate") requestData.mode = "same-origin";
    this._requestData = requestData;
  }
  /**
  * Returns a deep clone of the instance's `requestData` object.
  *
  * @returns
  */
  toObject() {
    const requestData = Object.assign({}, this._requestData);
    requestData.headers = Object.assign({}, this._requestData.headers);
    if (requestData.body) requestData.body = requestData.body.slice(0);
    return requestData;
  }
  /**
  * Converts this instance to a Request.
  *
  * @returns
  */
  toRequest() {
    return new Request(this._requestData.url, this._requestData);
  }
  /**
  * Creates and returns a deep clone of the instance.
  *
  * @returns
  */
  clone() {
    return new StorableRequest2(this.toObject());
  }
};
var TAG_PREFIX = "serwist-background-sync";
var MAX_RETENTION_TIME = 1440 * 7;
var queueNames = /* @__PURE__ */ new Set();
var convertEntry = (queueStoreEntry) => {
  const queueEntry = {
    request: new StorableRequest(queueStoreEntry.requestData).toRequest(),
    timestamp: queueStoreEntry.timestamp
  };
  if (queueStoreEntry.metadata) queueEntry.metadata = queueStoreEntry.metadata;
  return queueEntry;
};
var BackgroundSyncQueue = class {
  _name;
  _onSync;
  _maxRetentionTime;
  _queueStore;
  _forceSyncFallback;
  _syncInProgress = false;
  _requestsAddedDuringSync = false;
  /**
  * Creates an instance of Queue with the given options
  *
  * @param name The unique name for this queue. This name must be
  * unique as it's used to register sync events and store requests
  * in IndexedDB specific to this instance. An error will be thrown if
  * a duplicate name is detected.
  * @param options
  */
  constructor(name, { forceSyncFallback, onSync, maxRetentionTime } = {}) {
    if (queueNames.has(name)) throw new SerwistError("duplicate-queue-name", { name });
    queueNames.add(name);
    this._name = name;
    this._onSync = onSync || this.replayRequests;
    this._maxRetentionTime = maxRetentionTime || MAX_RETENTION_TIME;
    this._forceSyncFallback = Boolean(forceSyncFallback);
    this._queueStore = new BackgroundSyncQueueStore(this._name);
    this._addSyncListener();
  }
  /**
  * @returns
  */
  get name() {
    return this._name;
  }
  /**
  * Stores the passed request in IndexedDB (with its timestamp and any
  * metadata) at the end of the queue.
  *
  * @param entry
  */
  async pushRequest(entry) {
    if (true) {
      finalAssertExports.isType(entry, "object", {
        moduleName: "serwist",
        className: "BackgroundSyncQueue",
        funcName: "pushRequest",
        paramName: "entry"
      });
      finalAssertExports.isInstance(entry.request, Request, {
        moduleName: "serwist",
        className: "BackgroundSyncQueue",
        funcName: "pushRequest",
        paramName: "entry.request"
      });
    }
    await this._addRequest(entry, "push");
  }
  /**
  * Stores the passed request in IndexedDB (with its timestamp and any
  * metadata) at the beginning of the queue.
  *
  * @param entry
  */
  async unshiftRequest(entry) {
    if (true) {
      finalAssertExports.isType(entry, "object", {
        moduleName: "serwist",
        className: "BackgroundSyncQueue",
        funcName: "unshiftRequest",
        paramName: "entry"
      });
      finalAssertExports.isInstance(entry.request, Request, {
        moduleName: "serwist",
        className: "BackgroundSyncQueue",
        funcName: "unshiftRequest",
        paramName: "entry.request"
      });
    }
    await this._addRequest(entry, "unshift");
  }
  /**
  * Removes and returns the last request in the queue (along with its
  * timestamp and any metadata).
  *
  * @returns
  */
  async popRequest() {
    return this._removeRequest("pop");
  }
  /**
  * Removes and returns the first request in the queue (along with its
  * timestamp and any metadata).
  *
  * @returns
  */
  async shiftRequest() {
    return this._removeRequest("shift");
  }
  /**
  * Returns all the entries that have not expired (per `maxRetentionTime`).
  * Any expired entries are removed from the queue.
  *
  * @returns
  */
  async getAll() {
    const allEntries = await this._queueStore.getAll();
    const now = Date.now();
    const unexpiredEntries = [];
    for (const entry of allEntries) {
      const maxRetentionTimeInMs = this._maxRetentionTime * 60 * 1e3;
      if (now - entry.timestamp > maxRetentionTimeInMs) await this._queueStore.deleteEntry(entry.id);
      else unexpiredEntries.push(convertEntry(entry));
    }
    return unexpiredEntries;
  }
  /**
  * Returns the number of entries present in the queue.
  * Note that expired entries (per `maxRetentionTime`) are also included in this count.
  *
  * @returns
  */
  async size() {
    return await this._queueStore.size();
  }
  /**
  * Adds the entry to the QueueStore and registers for a sync event.
  *
  * @param entry
  * @param operation
  * @private
  */
  async _addRequest({ request, metadata, timestamp = Date.now() }, operation) {
    const entry = {
      requestData: (await StorableRequest.fromRequest(request.clone())).toObject(),
      timestamp
    };
    if (metadata) entry.metadata = metadata;
    switch (operation) {
      case "push":
        await this._queueStore.pushEntry(entry);
        break;
      case "unshift":
        await this._queueStore.unshiftEntry(entry);
        break;
    }
    if (true) logger.log(`Request for '${getFriendlyURL(request.url)}' has been added to background sync queue '${this._name}'.`);
    if (this._syncInProgress) this._requestsAddedDuringSync = true;
    else await this.registerSync();
  }
  /**
  * Removes and returns the first or last (depending on `operation`) entry
  * from the {@linkcode BackgroundSyncQueueStore} that's not older than the `maxRetentionTime`.
  *
  * @param operation
  * @returns
  * @private
  */
  async _removeRequest(operation) {
    const now = Date.now();
    let entry;
    switch (operation) {
      case "pop":
        entry = await this._queueStore.popEntry();
        break;
      case "shift":
        entry = await this._queueStore.shiftEntry();
        break;
    }
    if (entry) {
      const maxRetentionTimeInMs = this._maxRetentionTime * 60 * 1e3;
      if (now - entry.timestamp > maxRetentionTimeInMs) return this._removeRequest(operation);
      return convertEntry(entry);
    }
  }
  /**
  * Loops through each request in the queue and attempts to re-fetch it.
  * If any request fails to re-fetch, it's put back in the same position in
  * the queue (which registers a retry for the next sync event).
  */
  async replayRequests() {
    let entry;
    while (entry = await this.shiftRequest()) try {
      await fetch(entry.request.clone());
      if (true) logger.log(`Request for '${getFriendlyURL(entry.request.url)}' has been replayed in queue '${this._name}'`);
    } catch {
      await this.unshiftRequest(entry);
      if (true) logger.log(`Request for '${getFriendlyURL(entry.request.url)}' failed to replay, putting it back in queue '${this._name}'`);
      throw new SerwistError("queue-replay-failed", { name: this._name });
    }
    if (true) logger.log(`All requests in queue '${this.name}' have successfully replayed; the queue is now empty!`);
  }
  /**
  * Registers a sync event with a tag unique to this instance.
  */
  async registerSync() {
    if ("sync" in self.registration && !this._forceSyncFallback) try {
      await self.registration.sync.register(`${TAG_PREFIX}:${this._name}`);
    } catch (err) {
      if (true) logger.warn(`Unable to register sync event for '${this._name}'.`, err);
    }
  }
  /**
  * In sync-supporting browsers, this adds a listener for the sync event.
  * In non-sync-supporting browsers, or if _forceSyncFallback is true, this
  * will retry the queue on service worker startup.
  *
  * @private
  */
  _addSyncListener() {
    if ("sync" in self.registration && !this._forceSyncFallback) self.addEventListener("sync", (event) => {
      if (event.tag === `${TAG_PREFIX}:${this._name}`) {
        if (true) logger.log(`Background sync for tag '${event.tag}' has been received`);
        const syncComplete = async () => {
          this._syncInProgress = true;
          let syncError;
          try {
            await this._onSync({ queue: this });
          } catch (error) {
            if (error instanceof Error) {
              syncError = error;
              throw syncError;
            }
          } finally {
            if (this._requestsAddedDuringSync && !(syncError && !event.lastChance)) await this.registerSync();
            this._syncInProgress = false;
            this._requestsAddedDuringSync = false;
          }
        };
        event.waitUntil(syncComplete());
      }
    });
    else {
      if (true) logger.log("Background sync replaying without background sync event");
      this._onSync({ queue: this });
    }
  }
  /**
  * Returns the set of queue names. This is primarily used to reset the list
  * of queue names in tests.
  *
  * @returns
  * @private
  */
  static get _queueNames() {
    return queueNames;
  }
};
var BackgroundSyncPlugin = class {
  _queue;
  /**
  * @param name See the {@linkcode BackgroundSyncQueue}
  * documentation for parameter details.
  * @param options See the {@linkcode BackgroundSyncQueue}
  * documentation for parameter details.
  * @see https://serwist.pages.dev/docs/serwist/core/background-sync-queue
  */
  constructor(name, options) {
    this._queue = new BackgroundSyncQueue(name, options);
  }
  /**
  * @param options
  * @private
  */
  async fetchDidFail({ request }) {
    await this._queue.pushRequest({ request });
  }
};
var cacheOkAndOpaquePlugin = {
  /**
  * Returns a valid response (to allow caching) if the status is 200 (OK) or
  * 0 (opaque).
  *
  * @param options
  * @returns
  * @private
  */
  cacheWillUpdate: async ({ response }) => {
    if (response.status === 200 || response.status === 0) return response;
    return null;
  }
};
function toRequest(input) {
  return typeof input === "string" ? new Request(input) : input;
}
var StrategyHandler = class {
  /**
  * The event associated with this request.
  */
  event;
  /**
  * The request the strategy is processing (passed to the strategy's
  * `handle()` or `handleAll()` method).
  */
  request;
  /**
  * A `URL` instance of `request.url` (if passed to the strategy's
  * `handle()` or `handleAll()` method).
  * Note: the `url` param will be present if the strategy is invoked
  * from a {@linkcode Route} object.
  */
  url;
  /**
  * Some additional params (if passed to the strategy's
  * `handle()` or `handleAll()` method).
  *
  * Note: the `params` param will be present if the strategy is invoked
  * from a {@linkcode Route} object and that route's matcher returned a truthy
  * value (it will be that value).
  */
  params;
  _cacheKeys = {};
  _strategy;
  _handlerDeferred;
  _extendLifetimePromises;
  _plugins;
  _pluginStateMap;
  /**
  * Creates a new instance associated with the passed strategy and event
  * that's handling the request.
  *
  * The constructor also initializes the state that will be passed to each of
  * the plugins handling this request.
  *
  * @param strategy
  * @param options
  */
  constructor(strategy, options) {
    if (true) {
      finalAssertExports.isInstance(options.event, ExtendableEvent, {
        moduleName: "serwist",
        className: "StrategyHandler",
        funcName: "constructor",
        paramName: "options.event"
      });
      finalAssertExports.isInstance(options.request, Request, {
        moduleName: "serwist",
        className: "StrategyHandler",
        funcName: "constructor",
        paramName: "options.request"
      });
    }
    this.event = options.event;
    this.request = options.request;
    if (options.url) {
      this.url = options.url;
      this.params = options.params;
    }
    this._strategy = strategy;
    this._handlerDeferred = new Deferred();
    this._extendLifetimePromises = [];
    this._plugins = [...strategy.plugins];
    this._pluginStateMap = /* @__PURE__ */ new Map();
    for (const plugin of this._plugins) this._pluginStateMap.set(plugin, {});
    this.event.waitUntil(this._handlerDeferred.promise);
  }
  /**
  * Fetches a given request (and invokes any applicable plugin callback
  * methods), taking the `fetchOptions` (for non-navigation requests) and
  * `plugins` provided to the {@linkcode Strategy} object into account.
  *
  * The following plugin lifecycle methods are invoked when using this method:
  * - `requestWillFetch()`
  * - `fetchDidSucceed()`
  * - `fetchDidFail()`
  *
  * @param input The URL or request to fetch.
  * @returns
  */
  async fetch(input) {
    const { event } = this;
    let request = toRequest(input);
    const preloadResponse = await this.getPreloadResponse();
    if (preloadResponse) return preloadResponse;
    const originalRequest = this.hasCallback("fetchDidFail") ? request.clone() : null;
    try {
      for (const cb of this.iterateCallbacks("requestWillFetch")) request = await cb({
        request: request.clone(),
        event
      });
    } catch (err) {
      if (err instanceof Error) throw new SerwistError("plugin-error-request-will-fetch", { thrownErrorMessage: err.message });
    }
    const pluginFilteredRequest = request.clone();
    try {
      let fetchResponse;
      fetchResponse = await fetch(request, request.mode === "navigate" ? void 0 : this._strategy.fetchOptions);
      if (true) logger.debug(`Network request for '${getFriendlyURL(request.url)}' returned a response with status '${fetchResponse.status}'.`);
      for (const callback of this.iterateCallbacks("fetchDidSucceed")) fetchResponse = await callback({
        event,
        request: pluginFilteredRequest,
        response: fetchResponse
      });
      return fetchResponse;
    } catch (error) {
      if (true) logger.log(`Network request for '${getFriendlyURL(request.url)}' threw an error.`, error);
      if (originalRequest) await this.runCallbacks("fetchDidFail", {
        error,
        event,
        originalRequest: originalRequest.clone(),
        request: pluginFilteredRequest.clone()
      });
      throw error;
    }
  }
  /**
  * Calls `this.fetch()` and (in the background) caches the generated response.
  *
  * The call to `this.cachePut()` automatically invokes `this.waitUntil()`,
  * so you do not have to call `waitUntil()` yourself.
  *
  * @param input The request or URL to fetch and cache.
  * @returns
  */
  async fetchAndCachePut(input) {
    const response = await this.fetch(input);
    const responseClone = response.clone();
    this.waitUntil(this.cachePut(input, responseClone));
    return response;
  }
  /**
  * Matches a request from the cache (and invokes any applicable plugin
  * callback method) using the `cacheName`, `matchOptions`, and `plugins`
  * provided to the `Strategy` object.
  *
  * The following lifecycle methods are invoked when using this method:
  * - `cacheKeyWillBeUsed`
  * - `cachedResponseWillBeUsed`
  *
  * @param key The `Request` or `URL` object to use as the cache key.
  * @returns A matching response, if found.
  */
  async cacheMatch(key) {
    const request = toRequest(key);
    let cachedResponse;
    const { cacheName, matchOptions } = this._strategy;
    const effectiveRequest = await this.getCacheKey(request, "read");
    const multiMatchOptions = {
      ...matchOptions,
      cacheName
    };
    cachedResponse = await caches.match(effectiveRequest, multiMatchOptions);
    if (true) if (cachedResponse) logger.debug(`Found a cached response in '${cacheName}'.`);
    else logger.debug(`No cached response found in '${cacheName}'.`);
    for (const callback of this.iterateCallbacks("cachedResponseWillBeUsed")) cachedResponse = await callback({
      cacheName,
      matchOptions,
      cachedResponse,
      request: effectiveRequest,
      event: this.event
    }) || void 0;
    return cachedResponse;
  }
  /**
  * Puts a request/response pair into the cache (and invokes any applicable
  * plugin callback method) using the `cacheName` and `plugins` provided to
  * the {@linkcode Strategy} object.
  *
  * The following plugin lifecycle methods are invoked when using this method:
  * - `cacheKeyWillBeUsed`
  * - `cacheWillUpdate`
  * - `cacheDidUpdate`
  *
  * @param key The request or URL to use as the cache key.
  * @param response The response to cache.
  * @returns `false` if a `cacheWillUpdate` caused the response to
  * not be cached, and `true` otherwise.
  */
  async cachePut(key, response) {
    const request = toRequest(key);
    await timeout(0);
    const effectiveRequest = await this.getCacheKey(request, "write");
    if (true) {
      if (effectiveRequest.method && effectiveRequest.method !== "GET") throw new SerwistError("attempt-to-cache-non-get-request", {
        url: getFriendlyURL(effectiveRequest.url),
        method: effectiveRequest.method
      });
    }
    if (!response) {
      if (true) logger.error(`Cannot cache non-existent response for '${getFriendlyURL(effectiveRequest.url)}'.`);
      throw new SerwistError("cache-put-with-no-response", { url: getFriendlyURL(effectiveRequest.url) });
    }
    const responseToCache = await this._ensureResponseSafeToCache(response);
    if (!responseToCache) {
      if (true) logger.debug(`Response '${getFriendlyURL(effectiveRequest.url)}' will not be cached.`, responseToCache);
      return false;
    }
    const { cacheName, matchOptions } = this._strategy;
    const cache = await self.caches.open(cacheName);
    if (true) {
      const vary = response.headers.get("Vary");
      if (vary && matchOptions?.ignoreVary !== true) logger.debug(`The response for ${getFriendlyURL(effectiveRequest.url)} has a 'Vary: ${vary}' header. Consider setting the {ignoreVary: true} option on your strategy to ensure cache matching and deletion works as expected.`);
    }
    const hasCacheUpdateCallback = this.hasCallback("cacheDidUpdate");
    const oldResponse = hasCacheUpdateCallback ? await cacheMatchIgnoreParams(cache, effectiveRequest.clone(), ["__WB_REVISION__"], matchOptions) : null;
    if (true) logger.debug(`Updating the '${cacheName}' cache with a new Response for ${getFriendlyURL(effectiveRequest.url)}.`);
    try {
      await cache.put(effectiveRequest, hasCacheUpdateCallback ? responseToCache.clone() : responseToCache);
    } catch (error) {
      if (error instanceof Error) {
        if (error.name === "QuotaExceededError") await executeQuotaErrorCallbacks();
        throw error;
      }
    }
    for (const callback of this.iterateCallbacks("cacheDidUpdate")) await callback({
      cacheName,
      oldResponse,
      newResponse: responseToCache.clone(),
      request: effectiveRequest,
      event: this.event
    });
    return true;
  }
  /**
  * Checks the `plugins` provided to the {@linkcode Strategy} object for `cacheKeyWillBeUsed`
  * callbacks and executes found callbacks in sequence. The final `Request`
  * object returned by the last plugin is treated as the cache key for cache
  * reads and/or writes. If no `cacheKeyWillBeUsed` plugin callbacks have
  * been registered, the passed request is returned unmodified.
  *
  * @param request
  * @param mode
  * @returns
  */
  async getCacheKey(request, mode) {
    const key = `${request.url} | ${mode}`;
    if (!this._cacheKeys[key]) {
      let effectiveRequest = request;
      for (const callback of this.iterateCallbacks("cacheKeyWillBeUsed")) effectiveRequest = toRequest(await callback({
        mode,
        request: effectiveRequest,
        event: this.event,
        params: this.params
      }));
      this._cacheKeys[key] = effectiveRequest;
    }
    return this._cacheKeys[key];
  }
  /**
  * Returns `true` if the strategy has at least one plugin with the given
  * callback.
  *
  * @param name The name of the callback to check for.
  * @returns
  */
  hasCallback(name) {
    for (const plugin of this._strategy.plugins) if (name in plugin) return true;
    return false;
  }
  /**
  * Runs all plugin callbacks matching the given name, in order, passing the
  * given param object as the only argument.
  *
  * Note: since this method runs all plugins, it's not suitable for cases
  * where the return value of a callback needs to be applied prior to calling
  * the next callback. See {@linkcode StrategyHandler.iterateCallbacks} for how to handle that case.
  *
  * @param name The name of the callback to run within each plugin.
  * @param param The object to pass as the first (and only) param when executing each callback. This object will be merged with the
  * current plugin state prior to callback execution.
  */
  async runCallbacks(name, param) {
    for (const callback of this.iterateCallbacks(name)) await callback(param);
  }
  /**
  * Accepts a callback name and returns an iterable of matching plugin callbacks.
  *
  * @param name The name fo the callback to run
  * @returns
  */
  *iterateCallbacks(name) {
    for (const plugin of this._strategy.plugins) if (typeof plugin[name] === "function") {
      const state = this._pluginStateMap.get(plugin);
      const statefulCallback = (param) => {
        const statefulParam = {
          ...param,
          state
        };
        return plugin[name](statefulParam);
      };
      yield statefulCallback;
    }
  }
  /**
  * Adds a promise to the
  * [extend lifetime promises](https://w3c.github.io/ServiceWorker/#extendableevent-extend-lifetime-promises)
  * of the event event associated with the request being handled (usually a `FetchEvent`).
  *
  * Note: you can await {@linkcode StrategyHandler.doneWaiting} to know when all added promises have settled.
  *
  * @param promise A promise to add to the extend lifetime promises of
  * the event that triggered the request.
  */
  waitUntil(promise) {
    this._extendLifetimePromises.push(promise);
    return promise;
  }
  /**
  * Returns a promise that resolves once all promises passed to
  * `this.waitUntil()` have settled.
  *
  * Note: any work done after `doneWaiting()` settles should be manually
  * passed to an event's `waitUntil()` method (not `this.waitUntil()`), otherwise
  * the service worker thread may be killed prior to your work completing.
  */
  async doneWaiting() {
    let promise;
    while (promise = this._extendLifetimePromises.shift()) await promise;
  }
  /**
  * Stops running the strategy and immediately resolves any pending
  * `waitUntil()` promise.
  */
  destroy() {
    this._handlerDeferred.resolve(null);
  }
  /**
  * This method checks if the navigation preload `Response` is available.
  *
  * @param request
  * @param event
  * @returns
  */
  async getPreloadResponse() {
    if (this.event instanceof FetchEvent && this.event.request.mode === "navigate" && "preloadResponse" in this.event) try {
      const possiblePreloadResponse = await this.event.preloadResponse;
      if (possiblePreloadResponse) {
        if (true) logger.log(`Using a preloaded navigation response for '${getFriendlyURL(this.event.request.url)}'`);
        return possiblePreloadResponse;
      }
    } catch (error) {
      if (true) logger.error(error);
      return;
    }
  }
  /**
  * This method will call `cacheWillUpdate` on the available plugins (or use
  * status === 200) to determine if the response is safe and valid to cache.
  *
  * @param response
  * @returns
  * @private
  */
  async _ensureResponseSafeToCache(response) {
    let responseToCache = response;
    let pluginsUsed = false;
    for (const callback of this.iterateCallbacks("cacheWillUpdate")) {
      responseToCache = await callback({
        request: this.request,
        response: responseToCache,
        event: this.event
      }) || void 0;
      pluginsUsed = true;
      if (!responseToCache) break;
    }
    if (!pluginsUsed) {
      if (responseToCache && responseToCache.status !== 200) {
        if (true) if (responseToCache.status === 0) logger.warn(`The response for '${this.request.url}' is an opaque response. The caching strategy that you're using will not cache opaque responses by default.`);
        else logger.debug(`The response for '${this.request.url}' returned a status code of '${response.status}' and won't be cached as a result.`);
        responseToCache = void 0;
      }
    }
    return responseToCache;
  }
};
var Strategy = class {
  cacheName;
  plugins;
  fetchOptions;
  matchOptions;
  /**
  * Creates a new instance of the strategy and sets all documented option
  * properties as public instance properties.
  *
  * Note: if a custom strategy class extends the base Strategy class and does
  * not need more than these properties, it does not need to define its own
  * constructor.
  *
  * @param options
  */
  constructor(options = {}) {
    this.cacheName = cacheNames.getRuntimeName(options.cacheName);
    this.plugins = options.plugins || [];
    this.fetchOptions = options.fetchOptions;
    this.matchOptions = options.matchOptions;
  }
  /**
  * Performs a request strategy and returns a promise that will resolve to
  * a response, invoking all relevant plugin callbacks.
  *
  * When a strategy instance is registered with a route, this method is automatically
  * called when the route matches.
  *
  * Alternatively, this method can be used in a standalone `fetch` event
  * listener by passing it to `event.respondWith()`.
  *
  * @param options A `FetchEvent` or an object with the properties listed below.
  * @param options.request A request to run this strategy for.
  * @param options.event The event associated with the request.
  * @param options.url
  * @param options.params
  */
  handle(options) {
    const [responseDone] = this.handleAll(options);
    return responseDone;
  }
  /**
  * Similar to `handle()`, but instead of just returning a promise that
  * resolves to a response, it will return an tuple of `[response, done]` promises,
  * where `response` is equivalent to what `handle()` returns, and `done` is a
  * promise that will resolve once all promises added to `event.waitUntil()` as a part
  * of performing the strategy have completed.
  *
  * You can await the `done` promise to ensure any extra work performed by
  * the strategy (usually caching responses) completes successfully.
  *
  * @param options A `FetchEvent` or `HandlerCallbackOptions` object.
  * @returns A tuple of [response, done] promises that can be used to determine when the response resolves as
  * well as when the handler has completed all its work.
  */
  handleAll(options) {
    if (options instanceof FetchEvent) options = {
      event: options,
      request: options.request
    };
    const event = options.event;
    const request = typeof options.request === "string" ? new Request(options.request) : options.request;
    const handler = new StrategyHandler(this, options.url ? {
      event,
      request,
      url: options.url,
      params: options.params
    } : {
      event,
      request
    });
    const responseDone = this._getResponse(handler, request, event);
    return [responseDone, this._awaitComplete(responseDone, handler, request, event)];
  }
  async _getResponse(handler, request, event) {
    await handler.runCallbacks("handlerWillStart", {
      event,
      request
    });
    let response;
    try {
      response = await this._handle(request, handler);
      if (response === void 0 || response.type === "error") throw new SerwistError("no-response", { url: request.url });
    } catch (error) {
      if (error instanceof Error) for (const callback of handler.iterateCallbacks("handlerDidError")) {
        response = await callback({
          error,
          event,
          request
        });
        if (response !== void 0) break;
      }
      if (!response) throw error;
      if (true) throw logger.log(`While responding to '${getFriendlyURL(request.url)}', an ${error instanceof Error ? error.toString() : ""} error occurred. Using a fallback response provided by a handlerDidError plugin.`);
    }
    for (const callback of handler.iterateCallbacks("handlerWillRespond")) response = await callback({
      event,
      request,
      response
    });
    return response;
  }
  async _awaitComplete(responseDone, handler, request, event) {
    let response;
    let error;
    try {
      response = await responseDone;
    } catch {
    }
    try {
      await handler.runCallbacks("handlerDidRespond", {
        event,
        request,
        response
      });
      await handler.doneWaiting();
    } catch (waitUntilError) {
      if (waitUntilError instanceof Error) error = waitUntilError;
    }
    await handler.runCallbacks("handlerDidComplete", {
      event,
      request,
      response,
      error
    });
    handler.destroy();
    if (error) throw error;
  }
};
var messages2 = {
  strategyStart: (strategyName, request) => `Using ${strategyName} to respond to '${getFriendlyURL(request.url)}'`,
  printFinalResponse: (response) => {
    if (response) {
      logger.groupCollapsed("View the final response here.");
      logger.log(response || "[No response returned]");
      logger.groupEnd();
    }
  }
};
var NetworkFirst = class extends Strategy {
  _networkTimeoutSeconds;
  /**
  * @param options
  * This option can be used to combat
  * "[lie-fi](https://developers.google.com/web/fundamentals/performance/poor-connectivity/#lie-fi)"
  * scenarios.
  */
  constructor(options = {}) {
    super(options);
    if (!this.plugins.some((p) => "cacheWillUpdate" in p)) this.plugins.unshift(cacheOkAndOpaquePlugin);
    this._networkTimeoutSeconds = options.networkTimeoutSeconds || 0;
    if (true) {
      if (this._networkTimeoutSeconds) finalAssertExports.isType(this._networkTimeoutSeconds, "number", {
        moduleName: "serwist",
        className: this.constructor.name,
        funcName: "constructor",
        paramName: "networkTimeoutSeconds"
      });
    }
  }
  /**
  * @private
  * @param request A request to run this strategy for.
  * @param handler The event that triggered the request.
  * @returns
  */
  async _handle(request, handler) {
    const logs = [];
    if (true) finalAssertExports.isInstance(request, Request, {
      moduleName: "serwist",
      className: this.constructor.name,
      funcName: "handle",
      paramName: "makeRequest"
    });
    const promises = [];
    let timeoutId;
    if (this._networkTimeoutSeconds) {
      const { id, promise } = this._getTimeoutPromise({
        request,
        logs,
        handler
      });
      timeoutId = id;
      promises.push(promise);
    }
    const networkPromise = this._getNetworkPromise({
      timeoutId,
      request,
      logs,
      handler
    });
    promises.push(networkPromise);
    const response = await handler.waitUntil((async () => {
      return await handler.waitUntil(Promise.race(promises)) || await networkPromise;
    })());
    if (true) {
      logger.groupCollapsed(messages2.strategyStart(this.constructor.name, request));
      for (const log of logs) logger.log(log);
      messages2.printFinalResponse(response);
      logger.groupEnd();
    }
    if (!response) throw new SerwistError("no-response", { url: request.url });
    return response;
  }
  /**
  * @param options
  * @returns
  * @private
  */
  _getTimeoutPromise({ request, logs, handler }) {
    let timeoutId;
    return {
      promise: new Promise((resolve) => {
        const onNetworkTimeout = async () => {
          if (true) logs.push(`Timing out the network response at ${this._networkTimeoutSeconds} seconds.`);
          resolve(await handler.cacheMatch(request));
        };
        timeoutId = setTimeout(onNetworkTimeout, this._networkTimeoutSeconds * 1e3);
      }),
      id: timeoutId
    };
  }
  /**
  * @param options
  * @param options.timeoutId
  * @param options.request
  * @param options.logs A reference to the logs Array.
  * @param options.event
  * @returns
  *
  * @private
  */
  async _getNetworkPromise({ timeoutId, request, logs, handler }) {
    let error;
    let response;
    try {
      response = await handler.fetchAndCachePut(request);
    } catch (fetchError) {
      if (fetchError instanceof Error) error = fetchError;
    }
    if (timeoutId) clearTimeout(timeoutId);
    if (true) if (response) logs.push("Got response from network.");
    else logs.push("Unable to get a response from the network. Will respond with a cached response.");
    if (error || !response) {
      response = await handler.cacheMatch(request);
      if (true) if (response) logs.push(`Found a cached response in the '${this.cacheName}' cache.`);
      else logs.push(`No response found in the '${this.cacheName}' cache.`);
    }
    return response;
  }
};
var NetworkOnly = class extends Strategy {
  _networkTimeoutSeconds;
  /**
  * @param options
  */
  constructor(options = {}) {
    super(options);
    this._networkTimeoutSeconds = options.networkTimeoutSeconds || 0;
  }
  /**
  * @private
  * @param request A request to run this strategy for.
  * @param handler The event that triggered the request.
  * @returns
  */
  async _handle(request, handler) {
    if (true) finalAssertExports.isInstance(request, Request, {
      moduleName: "serwist",
      className: this.constructor.name,
      funcName: "_handle",
      paramName: "request"
    });
    let error;
    let response;
    try {
      const promises = [handler.fetch(request)];
      if (this._networkTimeoutSeconds) {
        const timeoutPromise = timeout(this._networkTimeoutSeconds * 1e3);
        promises.push(timeoutPromise);
      }
      response = await Promise.race(promises);
      if (!response) throw new Error(`Timed out the network response after ${this._networkTimeoutSeconds} seconds.`);
    } catch (err) {
      if (err instanceof Error) error = err;
    }
    if (true) {
      logger.groupCollapsed(messages2.strategyStart(this.constructor.name, request));
      if (response) logger.log("Got response from network.");
      else logger.log("Unable to get a response from the network.");
      messages2.printFinalResponse(response);
      logger.groupEnd();
    }
    if (!response) throw new SerwistError("no-response", {
      url: request.url,
      error
    });
    return response;
  }
};
var validMethods = [
  "DELETE",
  "GET",
  "HEAD",
  "PATCH",
  "POST",
  "PUT"
];
var normalizeHandler = (handler) => {
  if (handler && typeof handler === "object") {
    if (true) finalAssertExports.hasMethod(handler, "handle", {
      moduleName: "serwist",
      className: "Route",
      funcName: "constructor",
      paramName: "handler"
    });
    return handler;
  }
  if (true) finalAssertExports.isType(handler, "function", {
    moduleName: "serwist",
    className: "Route",
    funcName: "constructor",
    paramName: "handler"
  });
  return { handle: handler };
};
var Route = class {
  handler;
  match;
  method;
  catchHandler;
  /**
  * Constructor for Route class.
  *
  * @param match A callback function that determines whether the
  * route matches a given `fetch` event by returning a truthy value.
  * @param handler A callback function that returns a `Promise` resolving
  * to a `Response`.
  * @param method The HTTP method to match the route against. Defaults
  * to `GET`.
  */
  constructor(match, handler, method = "GET") {
    if (true) {
      finalAssertExports.isType(match, "function", {
        moduleName: "serwist",
        className: "Route",
        funcName: "constructor",
        paramName: "match"
      });
      if (method) finalAssertExports.isOneOf(method, validMethods, { paramName: "method" });
    }
    this.handler = normalizeHandler(handler);
    this.match = match;
    this.method = method;
  }
  /**
  *
  * @param handler A callback function that returns a Promise resolving
  * to a Response.
  */
  setCatchHandler(handler) {
    this.catchHandler = normalizeHandler(handler);
  }
};
var PrecacheStrategy = class PrecacheStrategy2 extends Strategy {
  _fallbackToNetwork;
  static defaultPrecacheCacheabilityPlugin = { async cacheWillUpdate({ response }) {
    if (!response || response.status >= 400) return null;
    return response;
  } };
  static copyRedirectedCacheableResponsesPlugin = { async cacheWillUpdate({ response }) {
    return response.redirected ? await copyResponse(response) : response;
  } };
  /**
  * @param options
  */
  constructor(options = {}) {
    options.cacheName = cacheNames.getPrecacheName(options.cacheName);
    super(options);
    this._fallbackToNetwork = options.fallbackToNetwork !== false;
    this.plugins.push(PrecacheStrategy2.copyRedirectedCacheableResponsesPlugin);
  }
  /**
  * @private
  * @param request A request to run this strategy for.
  * @param handler The event that triggered the request.
  * @returns
  */
  async _handle(request, handler) {
    const preloadResponse = await handler.getPreloadResponse();
    if (preloadResponse) return preloadResponse;
    const response = await handler.cacheMatch(request);
    if (response) return response;
    if (handler.event && handler.event.type === "install") return await this._handleInstall(request, handler);
    return await this._handleFetch(request, handler);
  }
  async _handleFetch(request, handler) {
    let response;
    const params = handler.params || {};
    if (this._fallbackToNetwork) {
      if (true) logger.warn(`The precached response for ${getFriendlyURL(request.url)} in ${this.cacheName} was not found. Falling back to the network.`);
      const integrityInManifest = params.integrity;
      const integrityInRequest = request.integrity;
      const noIntegrityConflict = !integrityInRequest || integrityInRequest === integrityInManifest;
      response = await handler.fetch(new Request(request, { integrity: request.mode !== "no-cors" ? integrityInRequest || integrityInManifest : void 0 }));
      if (integrityInManifest && noIntegrityConflict && request.mode !== "no-cors") {
        this._useDefaultCacheabilityPluginIfNeeded();
        const wasCached = await handler.cachePut(request, response.clone());
        if (true) {
          if (wasCached) logger.log(`A response for ${getFriendlyURL(request.url)} was used to "repair" the precache.`);
        }
      }
    } else throw new SerwistError("missing-precache-entry", {
      cacheName: this.cacheName,
      url: request.url
    });
    if (true) {
      const cacheKey = params.cacheKey || await handler.getCacheKey(request, "read");
      logger.groupCollapsed(`Precaching is responding to: ${getFriendlyURL(request.url)}`);
      logger.log(`Serving the precached url: ${getFriendlyURL(cacheKey instanceof Request ? cacheKey.url : cacheKey)}`);
      logger.groupCollapsed("View request details here.");
      logger.log(request);
      logger.groupEnd();
      logger.groupCollapsed("View response details here.");
      logger.log(response);
      logger.groupEnd();
      logger.groupEnd();
    }
    return response;
  }
  async _handleInstall(request, handler) {
    this._useDefaultCacheabilityPluginIfNeeded();
    const response = await handler.fetch(request);
    if (!await handler.cachePut(request, response.clone())) throw new SerwistError("bad-precaching-response", {
      url: request.url,
      status: response.status
    });
    return response;
  }
  /**
  * This method is complex, as there a number of things to account for:
  *
  * The `plugins` array can be set at construction, and/or it might be added to
  * to at any time before the strategy is used.
  *
  * At the time the strategy is used (i.e. during an `install` event), there
  * needs to be at least one plugin that implements `cacheWillUpdate` in the
  * array, other than `copyRedirectedCacheableResponsesPlugin`.
  *
  * - If this method is called and there are no suitable `cacheWillUpdate`
  * plugins, we need to add `defaultPrecacheCacheabilityPlugin`.
  *
  * - If this method is called and there is exactly one `cacheWillUpdate`, then
  * we don't have to do anything (this might be a previously added
  * `defaultPrecacheCacheabilityPlugin`, or it might be a custom plugin).
  *
  * - If this method is called and there is more than one `cacheWillUpdate`,
  * then we need to check if one is `defaultPrecacheCacheabilityPlugin`. If so,
  * we need to remove it. (This situation is unlikely, but it could happen if
  * the strategy is used multiple times, the first without a `cacheWillUpdate`,
  * and then later on after manually adding a custom `cacheWillUpdate`.)
  *
  * See https://github.com/GoogleChrome/workbox/issues/2737 for more context.
  *
  * @private
  */
  _useDefaultCacheabilityPluginIfNeeded() {
    let defaultPluginIndex = null;
    let cacheWillUpdatePluginCount = 0;
    for (const [index, plugin] of this.plugins.entries()) {
      if (plugin === PrecacheStrategy2.copyRedirectedCacheableResponsesPlugin) continue;
      if (plugin === PrecacheStrategy2.defaultPrecacheCacheabilityPlugin) defaultPluginIndex = index;
      if (plugin.cacheWillUpdate) cacheWillUpdatePluginCount++;
    }
    if (cacheWillUpdatePluginCount === 0) this.plugins.push(PrecacheStrategy2.defaultPrecacheCacheabilityPlugin);
    else if (cacheWillUpdatePluginCount > 1 && defaultPluginIndex !== null) this.plugins.splice(defaultPluginIndex, 1);
  }
};
var NavigationRoute = class extends Route {
  _allowlist;
  _denylist;
  /**
  * If both `denylist` and `allowlist` are provided, `denylist` will
  * take precedence.
  *
  * The regular expressions in `allowlist` and `denylist`
  * are matched against the concatenated
  * [`pathname`](https://developer.mozilla.org/en-US/docs/Web/API/HTMLHyperlinkElementUtils/pathname)
  * and [`search`](https://developer.mozilla.org/en-US/docs/Web/API/HTMLHyperlinkElementUtils/search)
  * portions of the requested URL.
  *
  * *Note*: These RegExps may be evaluated against every destination URL during
  * a navigation. Avoid using
  * [complex RegExps](https://github.com/GoogleChrome/workbox/issues/3077),
  * or else your users may see delays when navigating your site.
  *
  * @param handler A callback function that returns a `Promise` resulting in a `Response`.
  * @param options
  */
  constructor(handler, { allowlist = [/./], denylist = [] } = {}) {
    if (true) {
      finalAssertExports.isArrayOfClass(allowlist, RegExp, {
        moduleName: "serwist",
        className: "NavigationRoute",
        funcName: "constructor",
        paramName: "options.allowlist"
      });
      finalAssertExports.isArrayOfClass(denylist, RegExp, {
        moduleName: "serwist",
        className: "NavigationRoute",
        funcName: "constructor",
        paramName: "options.denylist"
      });
    }
    super((options) => this._match(options), handler);
    this._allowlist = allowlist;
    this._denylist = denylist;
  }
  /**
  * Routes match handler.
  *
  * @param options
  * @returns
  * @private
  */
  _match({ url, request }) {
    if (request && request.mode !== "navigate") return false;
    const pathnameAndSearch = url.pathname + url.search;
    for (const regExp of this._denylist) if (regExp.test(pathnameAndSearch)) {
      if (true) logger.log(`The navigation route ${pathnameAndSearch} is not being used, since the URL matches this denylist pattern: ${regExp.toString()}`);
      return false;
    }
    if (this._allowlist.some((regExp) => regExp.test(pathnameAndSearch))) {
      if (true) logger.debug(`The navigation route ${pathnameAndSearch} is being used.`);
      return true;
    }
    if (true) logger.log(`The navigation route ${pathnameAndSearch} is not being used, since the URL being navigated to doesn't match the allowlist.`);
    return false;
  }
};
var isNavigationPreloadSupported = () => {
  return Boolean(self.registration?.navigationPreload);
};
var enableNavigationPreload = (headerValue) => {
  if (isNavigationPreloadSupported()) self.addEventListener("activate", (event) => {
    event.waitUntil(self.registration.navigationPreload.enable().then(() => {
      if (headerValue) self.registration.navigationPreload.setHeaderValue(headerValue);
      if (true) logger.log("Navigation preloading is enabled.");
    }));
  });
  else if (true) logger.log("Navigation preloading is not supported in this browser.");
};
var removeIgnoredSearchParams = (urlObject, ignoreURLParametersMatching = []) => {
  for (const paramName of [...urlObject.searchParams.keys()]) if (ignoreURLParametersMatching.some((regExp) => regExp.test(paramName))) urlObject.searchParams.delete(paramName);
  return urlObject;
};
function* generateURLVariations(url, { directoryIndex = "index.html", ignoreURLParametersMatching = [/^utm_/, /^fbclid$/], cleanURLs = true, urlManipulation } = {}) {
  const urlObject = new URL(url, location.href);
  urlObject.hash = "";
  yield urlObject.href;
  const urlWithoutIgnoredParams = removeIgnoredSearchParams(urlObject, ignoreURLParametersMatching);
  yield urlWithoutIgnoredParams.href;
  if (directoryIndex && urlWithoutIgnoredParams.pathname.endsWith("/")) {
    const directoryURL = new URL(urlWithoutIgnoredParams.href);
    directoryURL.pathname += directoryIndex;
    yield directoryURL.href;
  }
  if (cleanURLs) {
    const cleanURL = new URL(urlWithoutIgnoredParams.href);
    cleanURL.pathname += ".html";
    yield cleanURL.href;
  }
  if (urlManipulation) {
    const additionalURLs = urlManipulation({ url: urlObject });
    for (const urlToAttempt of additionalURLs) yield urlToAttempt.href;
  }
}
var RegExpRoute = class extends Route {
  /**
  * If the regular expression contains
  * [capture groups](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/RegExp#grouping-back-references),
  * the captured values will be passed to the `params` argument.
  *
  * @param regExp The regular expression to match against URLs.
  * @param handler A callback function that returns a `Promise` resulting in a `Response`.
  * @param method The HTTP method to match the {@linkcode Route} against. Defaults to `GET`.
  * against.
  */
  constructor(regExp, handler, method) {
    if (true) finalAssertExports.isInstance(regExp, RegExp, {
      moduleName: "serwist",
      className: "RegExpRoute",
      funcName: "constructor",
      paramName: "pattern"
    });
    const match = ({ url }) => {
      const result = regExp.exec(url.href);
      if (!result) return;
      if (url.origin !== location.origin && result.index !== 0) {
        if (true) logger.debug(`The regular expression '${regExp.toString()}' only partially matched against the cross-origin URL '${url.toString()}'. RegExpRoute's will only handle cross-origin requests if they match the entire URL.`);
        return;
      }
      return result.slice(1);
    };
    super(match, handler, method);
  }
};
var setCacheNameDetails = (details) => {
  if (true) {
    for (const key of Object.keys(details)) finalAssertExports.isType(details[key], "string", {
      moduleName: "@serwist/core",
      funcName: "setCacheNameDetails",
      paramName: `details.${key}`
    });
    if (details.precache?.length === 0) throw new SerwistError("invalid-cache-name", {
      cacheNameId: "precache",
      value: details.precache
    });
    if (details.runtime?.length === 0) throw new SerwistError("invalid-cache-name", {
      cacheNameId: "runtime",
      value: details.runtime
    });
    if (details.googleAnalytics?.length === 0) throw new SerwistError("invalid-cache-name", {
      cacheNameId: "googleAnalytics",
      value: details.googleAnalytics
    });
  }
  cacheNames.updateDetails(details);
};
var REVISION_SEARCH_PARAM = "__WB_REVISION__";
var createCacheKey = (entry) => {
  if (!entry) throw new SerwistError("add-to-cache-list-unexpected-type", { entry });
  if (typeof entry === "string") {
    const urlObject = new URL(entry, location.href);
    return {
      cacheKey: urlObject.href,
      url: urlObject.href
    };
  }
  const { revision, url } = entry;
  if (!url) throw new SerwistError("add-to-cache-list-unexpected-type", { entry });
  if (!revision) {
    const urlObject = new URL(url, location.href);
    return {
      cacheKey: urlObject.href,
      url: urlObject.href
    };
  }
  const cacheKeyURL = new URL(url, location.href);
  const originalURL = new URL(url, location.href);
  cacheKeyURL.searchParams.set(REVISION_SEARCH_PARAM, revision);
  return {
    cacheKey: cacheKeyURL.href,
    url: originalURL.href
  };
};
var PrecacheInstallReportPlugin = class {
  updatedURLs = [];
  notUpdatedURLs = [];
  handlerWillStart = async ({ request, state }) => {
    if (state) state.originalRequest = request;
  };
  cachedResponseWillBeUsed = async ({ event, state, cachedResponse }) => {
    if (event.type === "install") {
      if (state?.originalRequest && state.originalRequest instanceof Request) {
        const url = state.originalRequest.url;
        if (cachedResponse) this.notUpdatedURLs.push(url);
        else this.updatedURLs.push(url);
      }
    }
    return cachedResponse;
  };
};
var parseRoute = (capture, handler, method) => {
  if (typeof capture === "string") {
    const captureUrl = new URL(capture, location.href);
    if (true) {
      if (!(capture.startsWith("/") || capture.startsWith("http"))) throw new SerwistError("invalid-string", {
        moduleName: "serwist",
        funcName: "parseRoute",
        paramName: "capture"
      });
      const valueToCheck = capture.startsWith("http") ? captureUrl.pathname : capture;
      const wildcards = "[*:?+]";
      if (new RegExp(`${wildcards}`).exec(valueToCheck)) logger.debug(`The '$capture' parameter contains an Express-style wildcard character (${wildcards}). Strings are now always interpreted as exact matches; use a RegExp for partial or wildcard matches.`);
    }
    const matchCallback = ({ url }) => {
      if (true) {
        if (url.pathname === captureUrl.pathname && url.origin !== captureUrl.origin) logger.debug(`${capture} only partially matches the cross-origin URL ${url.toString()}. This route will only handle cross-origin requests if they match the entire URL.`);
      }
      return url.href === captureUrl.href;
    };
    return new Route(matchCallback, handler, method);
  }
  if (capture instanceof RegExp) return new RegExpRoute(capture, handler, method);
  if (typeof capture === "function") return new Route(capture, handler, method);
  if (capture instanceof Route) return capture;
  throw new SerwistError("unsupported-route-type", {
    moduleName: "serwist",
    funcName: "parseRoute",
    paramName: "capture"
  });
};
var logGroup = (groupTitle, deletedURLs) => {
  logger.groupCollapsed(groupTitle);
  for (const url of deletedURLs) logger.log(url);
  logger.groupEnd();
};
var printCleanupDetails = (deletedURLs) => {
  const deletionCount = deletedURLs.length;
  if (deletionCount > 0) {
    logger.groupCollapsed(`During precaching cleanup, ${deletionCount} cached request${deletionCount === 1 ? " was" : "s were"} deleted.`);
    logGroup("Deleted Cache Requests", deletedURLs);
    logger.groupEnd();
  }
};
function _nestedGroup(groupTitle, urls) {
  if (urls.length === 0) return;
  logger.groupCollapsed(groupTitle);
  for (const url of urls) logger.log(url);
  logger.groupEnd();
}
var printInstallDetails = (urlsToPrecache, urlsAlreadyPrecached) => {
  const precachedCount = urlsToPrecache.length;
  const alreadyPrecachedCount = urlsAlreadyPrecached.length;
  if (precachedCount || alreadyPrecachedCount) {
    let message = `Precaching ${precachedCount} file${precachedCount === 1 ? "" : "s"}.`;
    if (alreadyPrecachedCount > 0) message += ` ${alreadyPrecachedCount} file${alreadyPrecachedCount === 1 ? " is" : "s are"} already cached.`;
    logger.groupCollapsed(message);
    _nestedGroup("View newly precached URLs.", urlsToPrecache);
    _nestedGroup("View previously precached URLs.", urlsAlreadyPrecached);
    logger.groupEnd();
  }
};

// node_modules/@serwist/utils/dist/index.mjs
var parallel = async (limit, array, func) => {
  const work = array.map((item, index) => ({
    index,
    item
  }));
  const processor = async (res) => {
    const results = [];
    while (true) {
      const next = work.pop();
      if (!next) return res(results);
      const result = await func(next.item);
      results.push({
        result,
        index: next.index
      });
    }
  };
  const queues = Array.from({ length: limit }, () => new Promise(processor));
  return (await Promise.all(queues)).flat().sort((a, b) => a.index < b.index ? -1 : 1).map((res) => res.result);
};

// node_modules/serwist/dist/index.mjs
var isSafari = typeof navigator !== "undefined" && /^((?!chrome|android).)*safari/i.test(navigator.userAgent);
var DB_NAME = "serwist-expiration";
var CACHE_OBJECT_STORE = "cache-entries";
var normalizeURL = (unNormalizedUrl) => {
  const url = new URL(unNormalizedUrl, location.href);
  url.hash = "";
  return url.href;
};
var CacheTimestampsModel = class {
  _cacheName;
  _db = null;
  /**
  *
  * @param cacheName
  *
  * @private
  */
  constructor(cacheName) {
    this._cacheName = cacheName;
  }
  /**
  * Takes a URL and returns an ID that will be unique in the object store.
  *
  * @param url
  * @returns
  * @private
  */
  _getId(url) {
    return `${this._cacheName}|${normalizeURL(url)}`;
  }
  /**
  * Performs an upgrade of indexedDB.
  *
  * @param db
  *
  * @private
  */
  _upgradeDb(db) {
    const objStore = db.createObjectStore(CACHE_OBJECT_STORE, { keyPath: "id" });
    objStore.createIndex("cacheName", "cacheName", { unique: false });
    objStore.createIndex("timestamp", "timestamp", { unique: false });
  }
  /**
  * Performs an upgrade of indexedDB and deletes deprecated DBs.
  *
  * @param db
  *
  * @private
  */
  _upgradeDbAndDeleteOldDbs(db) {
    this._upgradeDb(db);
    if (this._cacheName) deleteDB(this._cacheName);
  }
  /**
  * @param url
  * @param timestamp
  *
  * @private
  */
  async setTimestamp(url, timestamp) {
    url = normalizeURL(url);
    const entry = {
      id: this._getId(url),
      cacheName: this._cacheName,
      url,
      timestamp
    };
    const tx = (await this.getDb()).transaction(CACHE_OBJECT_STORE, "readwrite", { durability: "relaxed" });
    await tx.store.put(entry);
    await tx.done;
  }
  /**
  * Returns the timestamp stored for a given URL.
  *
  * @param url
  * @returns
  * @private
  */
  async getTimestamp(url) {
    return (await (await this.getDb()).get(CACHE_OBJECT_STORE, this._getId(url)))?.timestamp;
  }
  /**
  * Iterates through all the entries in the object store (from newest to
  * oldest) and removes entries once either `maxCount` is reached or the
  * entry's timestamp is less than `minTimestamp`.
  *
  * @param minTimestamp
  * @param maxCount
  * @returns
  * @private
  */
  async expireEntries(minTimestamp, maxCount) {
    let cursor = await (await this.getDb()).transaction(CACHE_OBJECT_STORE, "readwrite").store.index("timestamp").openCursor(null, "prev");
    const urlsDeleted = [];
    let entriesNotDeletedCount = 0;
    while (cursor) {
      const result = cursor.value;
      if (result.cacheName === this._cacheName) if (minTimestamp && result.timestamp < minTimestamp || maxCount && entriesNotDeletedCount >= maxCount) {
        cursor.delete();
        urlsDeleted.push(result.url);
      } else entriesNotDeletedCount++;
      cursor = await cursor.continue();
    }
    return urlsDeleted;
  }
  /**
  * Returns an open connection to the database.
  *
  * @private
  */
  async getDb() {
    if (!this._db) this._db = await openDB(DB_NAME, 1, { upgrade: this._upgradeDbAndDeleteOldDbs.bind(this) });
    return this._db;
  }
};
var CacheExpiration = class {
  _isRunning = false;
  _rerunRequested = false;
  _maxEntries;
  _maxAgeSeconds;
  _matchOptions;
  _cacheName;
  _timestampModel;
  /**
  * To construct a new `CacheExpiration` instance you must provide at least
  * one of the `config` properties.
  *
  * @param cacheName Name of the cache to apply restrictions to.
  * @param config
  */
  constructor(cacheName, config = {}) {
    if (true) {
      finalAssertExports.isType(cacheName, "string", {
        moduleName: "serwist",
        className: "CacheExpiration",
        funcName: "constructor",
        paramName: "cacheName"
      });
      if (!(config.maxEntries || config.maxAgeSeconds)) throw new SerwistError("max-entries-or-age-required", {
        moduleName: "serwist",
        className: "CacheExpiration",
        funcName: "constructor"
      });
      if (config.maxEntries) finalAssertExports.isType(config.maxEntries, "number", {
        moduleName: "serwist",
        className: "CacheExpiration",
        funcName: "constructor",
        paramName: "config.maxEntries"
      });
      if (config.maxAgeSeconds) finalAssertExports.isType(config.maxAgeSeconds, "number", {
        moduleName: "serwist",
        className: "CacheExpiration",
        funcName: "constructor",
        paramName: "config.maxAgeSeconds"
      });
    }
    this._maxEntries = config.maxEntries;
    this._maxAgeSeconds = config.maxAgeSeconds;
    this._matchOptions = config.matchOptions;
    this._cacheName = cacheName;
    this._timestampModel = new CacheTimestampsModel(cacheName);
  }
  /**
  * Expires entries for the given cache and given criteria.
  */
  async expireEntries() {
    if (this._isRunning) {
      this._rerunRequested = true;
      return;
    }
    this._isRunning = true;
    const minTimestamp = this._maxAgeSeconds ? Date.now() - this._maxAgeSeconds * 1e3 : 0;
    const urlsExpired = await this._timestampModel.expireEntries(minTimestamp, this._maxEntries);
    const cache = await self.caches.open(this._cacheName);
    for (const url of urlsExpired) await cache.delete(url, this._matchOptions);
    if (true) if (urlsExpired.length > 0) {
      logger.groupCollapsed(`Expired ${urlsExpired.length} ${urlsExpired.length === 1 ? "entry" : "entries"} and removed ${urlsExpired.length === 1 ? "it" : "them"} from the '${this._cacheName}' cache.`);
      logger.log(`Expired the following ${urlsExpired.length === 1 ? "URL" : "URLs"}:`);
      for (const url of urlsExpired) logger.log(`    ${url}`);
      logger.groupEnd();
    } else logger.debug("Cache expiration ran and found no entries to remove.");
    this._isRunning = false;
    if (this._rerunRequested) {
      this._rerunRequested = false;
      this.expireEntries();
    }
  }
  /**
  * Updates the timestamp for the given URL, allowing it to be correctly
  * tracked by the class.
  *
  * @param url
  */
  async updateTimestamp(url) {
    if (true) finalAssertExports.isType(url, "string", {
      moduleName: "serwist",
      className: "CacheExpiration",
      funcName: "updateTimestamp",
      paramName: "url"
    });
    await this._timestampModel.setTimestamp(url, Date.now());
  }
  /**
  * Checks if a URL has expired or not before it's used.
  *
  * This looks the timestamp up in IndexedDB and can be slow.
  *
  * Note: This method does not remove an expired entry, call
  * `expireEntries()` to remove such entries instead.
  *
  * @param url
  * @returns
  */
  async isURLExpired(url) {
    if (!this._maxAgeSeconds) {
      if (true) throw new SerwistError("expired-test-without-max-age", {
        methodName: "isURLExpired",
        paramName: "maxAgeSeconds"
      });
      return false;
    }
    const timestamp = await this._timestampModel.getTimestamp(url);
    const expireOlderThan = Date.now() - this._maxAgeSeconds * 1e3;
    return timestamp !== void 0 ? timestamp < expireOlderThan : true;
  }
  /**
  * Removes the IndexedDB used to keep track of cache expiration metadata.
  */
  async delete() {
    this._rerunRequested = false;
    await this._timestampModel.expireEntries(Number.POSITIVE_INFINITY);
  }
};
var registerQuotaErrorCallback = (callback) => {
  if (true) finalAssertExports.isType(callback, "function", {
    moduleName: "@serwist/core",
    funcName: "register",
    paramName: "callback"
  });
  quotaErrorCallbacks.add(callback);
  if (true) logger.log("Registered a callback to respond to quota errors.", callback);
};
var ExpirationPlugin = class {
  _config;
  _cacheExpirations;
  /**
  * @param config
  */
  constructor(config = {}) {
    if (true) {
      if (!(config.maxEntries || config.maxAgeSeconds)) throw new SerwistError("max-entries-or-age-required", {
        moduleName: "serwist",
        className: "ExpirationPlugin",
        funcName: "constructor"
      });
      if (config.maxEntries) finalAssertExports.isType(config.maxEntries, "number", {
        moduleName: "serwist",
        className: "ExpirationPlugin",
        funcName: "constructor",
        paramName: "config.maxEntries"
      });
      if (config.maxAgeSeconds) finalAssertExports.isType(config.maxAgeSeconds, "number", {
        moduleName: "serwist",
        className: "ExpirationPlugin",
        funcName: "constructor",
        paramName: "config.maxAgeSeconds"
      });
      if (config.maxAgeFrom) finalAssertExports.isType(config.maxAgeFrom, "string", {
        moduleName: "serwist",
        className: "ExpirationPlugin",
        funcName: "constructor",
        paramName: "config.maxAgeFrom"
      });
    }
    this._config = config;
    this._cacheExpirations = /* @__PURE__ */ new Map();
    if (!this._config.maxAgeFrom) this._config.maxAgeFrom = "last-fetched";
    if (this._config.purgeOnQuotaError) registerQuotaErrorCallback(() => this.deleteCacheAndMetadata());
  }
  /**
  * A simple helper method to return a CacheExpiration instance for a given
  * cache name.
  *
  * @param cacheName
  * @returns
  * @private
  */
  _getCacheExpiration(cacheName) {
    if (cacheName === cacheNames.getRuntimeName()) throw new SerwistError("expire-custom-caches-only");
    let cacheExpiration = this._cacheExpirations.get(cacheName);
    if (!cacheExpiration) {
      cacheExpiration = new CacheExpiration(cacheName, this._config);
      this._cacheExpirations.set(cacheName, cacheExpiration);
    }
    return cacheExpiration;
  }
  /**
  * A lifecycle callback that will be triggered automatically when a
  * response is about to be returned from a [`Cache`](https://developer.mozilla.org/en-US/docs/Web/API/Cache).
  * It allows the response to be inspected for freshness and
  * prevents it from being used if the response's `Date` header value is
  * older than the configured `maxAgeSeconds`.
  *
  * @param options
  * @returns `cachedResponse` if it is fresh and `null` if it is stale or
  * not available.
  * @private
  */
  cachedResponseWillBeUsed({ event, cacheName, request, cachedResponse }) {
    if (!cachedResponse) return null;
    const isFresh = this._isResponseDateFresh(cachedResponse);
    const cacheExpiration = this._getCacheExpiration(cacheName);
    const isMaxAgeFromLastUsed = this._config.maxAgeFrom === "last-used";
    const done = (async () => {
      if (isMaxAgeFromLastUsed) await cacheExpiration.updateTimestamp(request.url);
      await cacheExpiration.expireEntries();
    })();
    try {
      event.waitUntil(done);
    } catch {
      if (true) {
        if (event instanceof FetchEvent) logger.warn(`Unable to ensure service worker stays alive when updating cache entry for '${getFriendlyURL(event.request.url)}'.`);
      }
    }
    return isFresh ? cachedResponse : null;
  }
  /**
  * @param cachedResponse
  * @returns
  * @private
  */
  _isResponseDateFresh(cachedResponse) {
    if (this._config.maxAgeFrom === "last-used") return true;
    const now = Date.now();
    if (!this._config.maxAgeSeconds) return true;
    const dateHeaderTimestamp = this._getDateHeaderTimestamp(cachedResponse);
    if (dateHeaderTimestamp === null) return true;
    return dateHeaderTimestamp >= now - this._config.maxAgeSeconds * 1e3;
  }
  /**
  * Extracts the `Date` header and parse it into an useful value.
  *
  * @param cachedResponse
  * @returns
  * @private
  */
  _getDateHeaderTimestamp(cachedResponse) {
    if (!cachedResponse.headers.has("date")) return null;
    const dateHeader = cachedResponse.headers.get("date");
    const headerTime = new Date(dateHeader).getTime();
    if (Number.isNaN(headerTime)) return null;
    return headerTime;
  }
  /**
  * A lifecycle callback that will be triggered automatically when an entry is added
  * to a cache.
  *
  * @param options
  * @private
  */
  async cacheDidUpdate({ cacheName, request }) {
    if (true) {
      finalAssertExports.isType(cacheName, "string", {
        moduleName: "serwist",
        className: "Plugin",
        funcName: "cacheDidUpdate",
        paramName: "cacheName"
      });
      finalAssertExports.isInstance(request, Request, {
        moduleName: "serwist",
        className: "Plugin",
        funcName: "cacheDidUpdate",
        paramName: "request"
      });
    }
    const cacheExpiration = this._getCacheExpiration(cacheName);
    await cacheExpiration.updateTimestamp(request.url);
    await cacheExpiration.expireEntries();
  }
  /**
  * Deletes the underlying `Cache` instance associated with this instance and the metadata
  * from IndexedDB used to keep track of expiration details for each `Cache` instance.
  *
  * When using cache expiration, calling this method is preferable to calling
  * `caches.delete()` directly, since this will ensure that the IndexedDB
  * metadata is also cleanly removed and that open IndexedDB instances are deleted.
  *
  * Note that if you're *not* using cache expiration for a given cache, calling
  * `caches.delete()` and passing in the cache's name should be sufficient.
  * There is no Serwist-specific method needed for cleanup in that case.
  */
  async deleteCacheAndMetadata() {
    for (const [cacheName, cacheExpiration] of this._cacheExpirations) {
      await self.caches.delete(cacheName);
      await cacheExpiration.delete();
    }
    this._cacheExpirations = /* @__PURE__ */ new Map();
  }
};

// node_modules/@serwist/next/dist/index.worker.mjs
var defaultCache = true ? [{
  matcher: /.*/i,
  handler: new NetworkOnly()
}] : [
  {
    matcher: /^https:\/\/fonts\.(?:gstatic)\.com\/.*/i,
    handler: new CacheFirst({
      cacheName: "google-fonts-webfonts",
      plugins: [new ExpirationPlugin({
        maxEntries: 4,
        maxAgeSeconds: 365 * 24 * 60 * 60,
        maxAgeFrom: "last-used"
      })]
    })
  },
  {
    matcher: /^https:\/\/fonts\.(?:googleapis)\.com\/.*/i,
    handler: new StaleWhileRevalidate({
      cacheName: "google-fonts-stylesheets",
      plugins: [new ExpirationPlugin({
        maxEntries: 4,
        maxAgeSeconds: 10080 * 60,
        maxAgeFrom: "last-used"
      })]
    })
  },
  {
    matcher: /\.(?:eot|otf|ttc|ttf|woff|woff2|font.css)$/i,
    handler: new StaleWhileRevalidate({
      cacheName: "static-font-assets",
      plugins: [new ExpirationPlugin({
        maxEntries: 4,
        maxAgeSeconds: 10080 * 60,
        maxAgeFrom: "last-used"
      })]
    })
  },
  {
    matcher: /\.(?:jpg|jpeg|gif|png|svg|ico|webp)$/i,
    handler: new StaleWhileRevalidate({
      cacheName: "static-image-assets",
      plugins: [new ExpirationPlugin({
        maxEntries: 64,
        maxAgeSeconds: 720 * 60 * 60,
        maxAgeFrom: "last-used"
      })]
    })
  },
  {
    matcher: /\/_next\/static.+\.js$/i,
    handler: new CacheFirst({
      cacheName: "next-static-js-assets",
      plugins: [new ExpirationPlugin({
        maxEntries: 64,
        maxAgeSeconds: 1440 * 60,
        maxAgeFrom: "last-used"
      })]
    })
  },
  {
    matcher: /\/_next\/image\?url=.+$/i,
    handler: new StaleWhileRevalidate({
      cacheName: "next-image",
      plugins: [new ExpirationPlugin({
        maxEntries: 64,
        maxAgeSeconds: 1440 * 60,
        maxAgeFrom: "last-used"
      })]
    })
  },
  {
    matcher: /\.(?:mp3|wav|ogg)$/i,
    handler: new CacheFirst({
      cacheName: "static-audio-assets",
      plugins: [new ExpirationPlugin({
        maxEntries: 32,
        maxAgeSeconds: 1440 * 60,
        maxAgeFrom: "last-used"
      }), new RangeRequestsPlugin()]
    })
  },
  {
    matcher: /\.(?:mp4|webm)$/i,
    handler: new CacheFirst({
      cacheName: "static-video-assets",
      plugins: [new ExpirationPlugin({
        maxEntries: 32,
        maxAgeSeconds: 1440 * 60,
        maxAgeFrom: "last-used"
      }), new RangeRequestsPlugin()]
    })
  },
  {
    matcher: /\.(?:js)$/i,
    handler: new StaleWhileRevalidate({
      cacheName: "static-js-assets",
      plugins: [new ExpirationPlugin({
        maxEntries: 48,
        maxAgeSeconds: 1440 * 60,
        maxAgeFrom: "last-used"
      })]
    })
  },
  {
    matcher: /\.(?:css|less)$/i,
    handler: new StaleWhileRevalidate({
      cacheName: "static-style-assets",
      plugins: [new ExpirationPlugin({
        maxEntries: 32,
        maxAgeSeconds: 1440 * 60,
        maxAgeFrom: "last-used"
      })]
    })
  },
  {
    matcher: /\/_next\/data\/.+\/.+\.json$/i,
    handler: new NetworkFirst({
      cacheName: "next-data",
      plugins: [new ExpirationPlugin({
        maxEntries: 32,
        maxAgeSeconds: 1440 * 60,
        maxAgeFrom: "last-used"
      })]
    })
  },
  {
    matcher: /\.(?:json|xml|csv)$/i,
    handler: new NetworkFirst({
      cacheName: "static-data-assets",
      plugins: [new ExpirationPlugin({
        maxEntries: 32,
        maxAgeSeconds: 1440 * 60,
        maxAgeFrom: "last-used"
      })]
    })
  },
  {
    matcher: /\/api\/auth\/.*/,
    handler: new NetworkOnly({ networkTimeoutSeconds: 10 })
  },
  {
    matcher: ({ sameOrigin, url: { pathname } }) => sameOrigin && pathname.startsWith("/api/"),
    method: "GET",
    handler: new NetworkFirst({
      cacheName: "apis",
      plugins: [new ExpirationPlugin({
        maxEntries: 16,
        maxAgeSeconds: 1440 * 60,
        maxAgeFrom: "last-used"
      })],
      networkTimeoutSeconds: 10
    })
  },
  {
    matcher: ({ request, url: { pathname }, sameOrigin }) => request.headers.get("RSC") === "1" && request.headers.get("Next-Router-Prefetch") === "1" && sameOrigin && !pathname.startsWith("/api/"),
    handler: new NetworkFirst({
      cacheName: PAGES_CACHE_NAME.rscPrefetch,
      plugins: [new ExpirationPlugin({
        maxEntries: 32,
        maxAgeSeconds: 1440 * 60
      })]
    })
  },
  {
    matcher: ({ request, url: { pathname }, sameOrigin }) => request.headers.get("RSC") === "1" && sameOrigin && !pathname.startsWith("/api/"),
    handler: new NetworkFirst({
      cacheName: PAGES_CACHE_NAME.rsc,
      plugins: [new ExpirationPlugin({
        maxEntries: 32,
        maxAgeSeconds: 1440 * 60
      })]
    })
  },
  {
    matcher: ({ request, url: { pathname }, sameOrigin }) => request.headers.get("Content-Type")?.includes("text/html") && sameOrigin && !pathname.startsWith("/api/"),
    handler: new NetworkFirst({
      cacheName: PAGES_CACHE_NAME.html,
      plugins: [new ExpirationPlugin({
        maxEntries: 32,
        maxAgeSeconds: 1440 * 60
      })]
    })
  },
  {
    matcher: ({ url: { pathname }, sameOrigin }) => sameOrigin && !pathname.startsWith("/api/"),
    handler: new NetworkFirst({
      cacheName: "others",
      plugins: [new ExpirationPlugin({
        maxEntries: 32,
        maxAgeSeconds: 1440 * 60
      })]
    })
  },
  {
    matcher: ({ sameOrigin }) => !sameOrigin,
    handler: new NetworkFirst({
      cacheName: "cross-origin",
      plugins: [new ExpirationPlugin({
        maxEntries: 32,
        maxAgeSeconds: 3600
      })],
      networkTimeoutSeconds: 10
    })
  },
  {
    matcher: /.*/i,
    method: "GET",
    handler: new NetworkOnly()
  }
];

// node_modules/serwist/dist/index.legacy.mjs
var PrecacheCacheKeyPlugin = class {
  _precacheController;
  constructor({ precacheController }) {
    this._precacheController = precacheController;
  }
  cacheKeyWillBeUsed = async ({ request, params }) => {
    const cacheKey = params?.cacheKey || this._precacheController.getCacheKeyForURL(request.url);
    return cacheKey ? new Request(cacheKey, { headers: request.headers }) : request;
  };
};
var PrecacheController = class {
  _installAndActiveListenersAdded;
  _concurrentPrecaching;
  _strategy;
  _urlsToCacheKeys = /* @__PURE__ */ new Map();
  _urlsToCacheModes = /* @__PURE__ */ new Map();
  _cacheKeysToIntegrities = /* @__PURE__ */ new Map();
  /**
  * Create a new PrecacheController.
  *
  * @param options
  */
  constructor({ cacheName, plugins = [], fallbackToNetwork = true, concurrentPrecaching = 1 } = {}) {
    this._concurrentPrecaching = concurrentPrecaching;
    this._strategy = new PrecacheStrategy({
      cacheName: cacheNames.getPrecacheName(cacheName),
      plugins: [...plugins, new PrecacheCacheKeyPlugin({ precacheController: this })],
      fallbackToNetwork
    });
    this.install = this.install.bind(this);
    this.activate = this.activate.bind(this);
  }
  /**
  * The strategy created by this controller and
  * used to cache assets and respond to `fetch` events.
  */
  get strategy() {
    return this._strategy;
  }
  /**
  * Adds items to the precache list, removing any duplicates and
  * stores the files in the precache cache when the service
  * worker installs.
  *
  * This method can be called multiple times.
  *
  * @param entries Array of entries to precache.
  */
  precache(entries) {
    this.addToCacheList(entries);
    if (!this._installAndActiveListenersAdded) {
      self.addEventListener("install", this.install);
      self.addEventListener("activate", this.activate);
      this._installAndActiveListenersAdded = true;
    }
  }
  /**
  * This method will add items to the precache list, removing duplicates
  * and ensuring the information is valid.
  *
  * @param entries Array of entries to precache.
  */
  addToCacheList(entries) {
    if (true) finalAssertExports.isArray(entries, {
      moduleName: "serwist/legacy",
      className: "PrecacheController",
      funcName: "addToCacheList",
      paramName: "entries"
    });
    const urlsToWarnAbout = [];
    for (const entry of entries) {
      if (typeof entry === "string") urlsToWarnAbout.push(entry);
      else if (entry && !entry.integrity && entry.revision === void 0) urlsToWarnAbout.push(entry.url);
      const { cacheKey, url } = createCacheKey(entry);
      const cacheMode = typeof entry !== "string" && entry.revision ? "reload" : "default";
      if (this._urlsToCacheKeys.has(url) && this._urlsToCacheKeys.get(url) !== cacheKey) throw new SerwistError("add-to-cache-list-conflicting-entries", {
        firstEntry: this._urlsToCacheKeys.get(url),
        secondEntry: cacheKey
      });
      if (typeof entry !== "string" && entry.integrity) {
        if (this._cacheKeysToIntegrities.has(cacheKey) && this._cacheKeysToIntegrities.get(cacheKey) !== entry.integrity) throw new SerwistError("add-to-cache-list-conflicting-integrities", { url });
        this._cacheKeysToIntegrities.set(cacheKey, entry.integrity);
      }
      this._urlsToCacheKeys.set(url, cacheKey);
      this._urlsToCacheModes.set(url, cacheMode);
      if (urlsToWarnAbout.length > 0) {
        const warningMessage = `Serwist is precaching URLs without revision info: ${urlsToWarnAbout.join(", ")}
This is generally NOT safe. Learn more at https://bit.ly/wb-precache`;
        if (false) console.warn(warningMessage);
        else logger.warn(warningMessage);
      }
    }
  }
  /**
  * Precaches new and updated assets. Call this method from the service worker
  * install event.
  *
  * Note: this method calls `event.waitUntil()` for you, so you do not need
  * to call it yourself in your event handlers.
  *
  * @param event
  * @returns
  */
  install(event) {
    return waitUntil(event, async () => {
      const installReportPlugin = new PrecacheInstallReportPlugin();
      this.strategy.plugins.push(installReportPlugin);
      await parallel(this._concurrentPrecaching, Array.from(this._urlsToCacheKeys.entries()), async ([url, cacheKey]) => {
        const integrity = this._cacheKeysToIntegrities.get(cacheKey);
        const cacheMode = this._urlsToCacheModes.get(url);
        const request = new Request(url, {
          integrity,
          cache: cacheMode,
          credentials: "same-origin"
        });
        await Promise.all(this.strategy.handleAll({
          event,
          request,
          url: new URL(request.url),
          params: { cacheKey }
        }));
      });
      const { updatedURLs, notUpdatedURLs } = installReportPlugin;
      if (true) printInstallDetails(updatedURLs, notUpdatedURLs);
      return {
        updatedURLs,
        notUpdatedURLs
      };
    });
  }
  /**
  * Deletes assets that are no longer present in the current precache manifest.
  * Call this method from the service worker activate event.
  *
  * Note: this method calls `event.waitUntil()` for you, so you do not need
  * to call it yourself in your event handlers.
  *
  * @param event
  * @returns
  */
  activate(event) {
    return waitUntil(event, async () => {
      const cache = await self.caches.open(this.strategy.cacheName);
      const currentlyCachedRequests = await cache.keys();
      const expectedCacheKeys = new Set(this._urlsToCacheKeys.values());
      const deletedCacheRequests = [];
      for (const request of currentlyCachedRequests) if (!expectedCacheKeys.has(request.url)) {
        await cache.delete(request);
        deletedCacheRequests.push(request.url);
      }
      if (true) printCleanupDetails(deletedCacheRequests);
      return { deletedCacheRequests };
    });
  }
  /**
  * Returns a mapping of a precached URL to the corresponding cache key, taking
  * into account the revision information for the URL.
  *
  * @returns A URL to cache key mapping.
  */
  getURLsToCacheKeys() {
    return this._urlsToCacheKeys;
  }
  /**
  * Returns a list of all the URLs that have been precached by the current
  * service worker.
  *
  * @returns The precached URLs.
  */
  getCachedURLs() {
    return [...this._urlsToCacheKeys.keys()];
  }
  /**
  * Returns the cache key used for storing a given URL. If that URL is
  * unversioned, like `/index.html', then the cache key will be the original
  * URL with a search parameter appended to it.
  *
  * @param url A URL whose cache key you want to look up.
  * @returns The versioned URL that corresponds to a cache key
  * for the original URL, or undefined if that URL isn't precached.
  */
  getCacheKeyForURL(url) {
    const urlObject = new URL(url, location.href);
    return this._urlsToCacheKeys.get(urlObject.href);
  }
  /**
  * @param url A cache key whose SRI you want to look up.
  * @returns The subresource integrity associated with the cache key,
  * or undefined if it's not set.
  */
  getIntegrityForCacheKey(cacheKey) {
    return this._cacheKeysToIntegrities.get(cacheKey);
  }
  /**
  * This acts as a drop-in replacement for
  * [`cache.match()`](https://developer.mozilla.org/en-US/docs/Web/API/Cache/match)
  * with the following differences:
  *
  * - It knows what the name of the precache is, and only checks in that cache.
  * - It allows you to pass in an "original" URL without versioning parameters,
  * and it will automatically look up the correct cache key for the currently
  * active revision of that URL.
  *
  * E.g., `matchPrecache('index.html')` will find the correct precached
  * response for the currently active service worker, even if the actual cache
  * key is `'/index.html?__WB_REVISION__=1234abcd'`.
  *
  * @param request The key (without revisioning parameters)
  * to look up in the precache.
  * @returns
  */
  async matchPrecache(request) {
    const url = request instanceof Request ? request.url : request;
    const cacheKey = this.getCacheKeyForURL(url);
    if (cacheKey) return (await self.caches.open(this.strategy.cacheName)).match(cacheKey);
  }
  /**
  * Returns a function that looks up `url` in the precache (taking into
  * account revision information), and returns the corresponding `Response`.
  *
  * @param url The precached URL which will be used to lookup the response.
  * @return
  */
  createHandlerBoundToURL(url) {
    const cacheKey = this.getCacheKeyForURL(url);
    if (!cacheKey) throw new SerwistError("non-precached-url", { url });
    return (options) => {
      options.request = new Request(url);
      options.params = {
        cacheKey,
        ...options.params
      };
      return this.strategy.handle(options);
    };
  }
};
var defaultPrecacheController;
var getSingletonPrecacheController = () => {
  if (!defaultPrecacheController) defaultPrecacheController = new PrecacheController();
  return defaultPrecacheController;
};
var PrecacheRoute = class extends Route {
  /**
  * @param precacheController A {@linkcode PrecacheController}
  * instance used to both match requests and respond to `fetch` events.
  * @param options Options to control how requests are matched
  * against the list of precached URLs.
  */
  constructor(precacheController, options) {
    const match = ({ request }) => {
      const urlsToCacheKeys = precacheController.getURLsToCacheKeys();
      for (const possibleURL of generateURLVariations(request.url, options)) {
        const cacheKey = urlsToCacheKeys.get(possibleURL);
        if (cacheKey) return {
          cacheKey,
          integrity: precacheController.getIntegrityForCacheKey(cacheKey)
        };
      }
      if (true) logger.debug(`Precaching did not find a match for ${getFriendlyURL(request.url)}`);
    };
    super(match, precacheController.strategy);
  }
};
var Router = class {
  _routes;
  _defaultHandlerMap;
  _fetchListenerHandler = null;
  _cacheListenerHandler = null;
  _catchHandler;
  /**
  * Initializes a new Router.
  */
  constructor() {
    this._routes = /* @__PURE__ */ new Map();
    this._defaultHandlerMap = /* @__PURE__ */ new Map();
  }
  /**
  * @returns routes A `Map` of HTTP method name (`'GET'`, etc.) to an array of all
  * the corresponding {@linkcode Route} instances that are registered.
  */
  get routes() {
    return this._routes;
  }
  /**
  * Adds a `fetch` event listener to respond to events when a route matches
  * the event's request. Effectively no-op if `addFetchListener` has been
  * called, but `removeFetchListener` has not.
  */
  addFetchListener() {
    if (!this._fetchListenerHandler) {
      this._fetchListenerHandler = (event) => {
        const { request } = event;
        const responsePromise = this.handleRequest({
          request,
          event
        });
        if (responsePromise) event.respondWith(responsePromise);
      };
      self.addEventListener("fetch", this._fetchListenerHandler);
    }
  }
  /**
  * Removes `fetch` event listener added by `addFetchListener`.
  * Effectively no-op if either `addFetchListener` has not been called or,
  * if it has, so has `removeFetchListener`.
  */
  removeFetchListener() {
    if (this._fetchListenerHandler) {
      self.removeEventListener("fetch", this._fetchListenerHandler);
      this._fetchListenerHandler = null;
    }
  }
  /**
  * Adds a `message` event listener for URLs to cache from the window.
  * This is useful to cache resources loaded on the page prior to when the
  * service worker started controlling it. Effectively no-op if `addCacheListener`
  * has been called, but `removeCacheListener` hasn't.
  *
  * The format of the message data sent from the window should be as follows.
  * Where the `urlsToCache` array may consist of URL strings or an array of
  * URL string + `requestInit` object (the same as you'd pass to `fetch()`).
  *
  * ```
  * {
  *   type: 'CACHE_URLS',
  *   payload: {
  *     urlsToCache: [
  *       './script1.js',
  *       './script2.js',
  *       ['./script3.js', {mode: 'no-cors'}],
  *     ],
  *   },
  * }
  * ```
  */
  addCacheListener() {
    if (!this._cacheListenerHandler) {
      this._cacheListenerHandler = (event) => {
        if (event.data && event.data.type === "CACHE_URLS") {
          const { payload } = event.data;
          if (true) logger.debug("Caching URLs from the window", payload.urlsToCache);
          const requestPromises = Promise.all(payload.urlsToCache.map((entry) => {
            if (typeof entry === "string") entry = [entry];
            const request = new Request(...entry);
            return this.handleRequest({
              request,
              event
            });
          }));
          event.waitUntil(requestPromises);
          if (event.ports?.[0]) requestPromises.then(() => event.ports[0].postMessage(true));
        }
      };
      self.addEventListener("message", this._cacheListenerHandler);
    }
  }
  /**
  * Removes the `message` event listener added by `addCacheListener`.
  * Effectively no-op if either `addCacheListener` has not been called or,
  * if it has, so has `removeCacheListener`.
  */
  removeCacheListener() {
    if (this._cacheListenerHandler) self.removeEventListener("message", this._cacheListenerHandler);
  }
  /**
  * Apply the routing rules to a `fetch` event to get a response from an
  * appropriate route.
  *
  * @param options
  * @returns A promise is returned if a registered route can handle the request.
  * If there is no matching route and there's no `defaultHandler`, `undefined`
  * is returned.
  */
  handleRequest({ request, event }) {
    if (true) finalAssertExports.isInstance(request, Request, {
      moduleName: "serwist/legacy",
      className: "Router",
      funcName: "handleRequest",
      paramName: "options.request"
    });
    const url = new URL(request.url, location.href);
    if (!url.protocol.startsWith("http")) {
      if (true) logger.debug("Router only supports URLs that start with 'http'.");
      return;
    }
    const sameOrigin = url.origin === location.origin;
    const { params, route } = this.findMatchingRoute({
      event,
      request,
      sameOrigin,
      url
    });
    let handler = route?.handler;
    const debugMessages = [];
    if (true) {
      if (handler) {
        debugMessages.push(["Found a route to handle this request:", route]);
        if (params) debugMessages.push([`Passing the following params to the route's handler:`, params]);
      }
    }
    const method = request.method;
    if (!handler && this._defaultHandlerMap.has(method)) {
      if (true) debugMessages.push(`Failed to find a matching route. Falling back to the default handler for ${method}.`);
      handler = this._defaultHandlerMap.get(method);
    }
    if (!handler) {
      if (true) logger.debug(`No route found for: ${getFriendlyURL(url)}`);
      return;
    }
    if (true) {
      logger.groupCollapsed(`Router is responding to: ${getFriendlyURL(url)}`);
      for (const msg of debugMessages) if (Array.isArray(msg)) logger.log(...msg);
      else logger.log(msg);
      logger.groupEnd();
    }
    let responsePromise;
    try {
      responsePromise = handler.handle({
        url,
        request,
        event,
        params
      });
    } catch (err) {
      responsePromise = Promise.reject(err);
    }
    const catchHandler = route?.catchHandler;
    if (responsePromise instanceof Promise && (this._catchHandler || catchHandler)) responsePromise = responsePromise.catch(async (err) => {
      if (catchHandler) {
        if (true) {
          logger.groupCollapsed(`Error thrown when responding to:  ${getFriendlyURL(url)}. Falling back to route's Catch Handler.`);
          logger.error("Error thrown by:", route);
          logger.error(err);
          logger.groupEnd();
        }
        try {
          return await catchHandler.handle({
            url,
            request,
            event,
            params
          });
        } catch (catchErr) {
          if (catchErr instanceof Error) err = catchErr;
        }
      }
      if (this._catchHandler) {
        if (true) {
          logger.groupCollapsed(`Error thrown when responding to:  ${getFriendlyURL(url)}. Falling back to global Catch Handler.`);
          logger.error("Error thrown by:", route);
          logger.error(err);
          logger.groupEnd();
        }
        return this._catchHandler.handle({
          url,
          request,
          event
        });
      }
      throw err;
    });
    return responsePromise;
  }
  /**
  * Checks a request and URL (and optionally an event) against the list of
  * registered routes, and if there's a match, returns the corresponding
  * route along with any params generated by the match.
  *
  * @param options
  * @returns An object with `route` and `params` properties. They are populated
  * if a matching route was found or `undefined` otherwise.
  */
  findMatchingRoute({ url, sameOrigin, request, event }) {
    const routes = this._routes.get(request.method) || [];
    for (const route of routes) {
      let params;
      const matchResult = route.match({
        url,
        sameOrigin,
        request,
        event
      });
      if (matchResult) {
        if (true) {
          if (matchResult instanceof Promise) logger.warn(`While routing ${getFriendlyURL(url)}, an async matchCallback function was used. Please convert the following route to use a synchronous matchCallback function:`, route);
        }
        params = matchResult;
        if (Array.isArray(params) && params.length === 0) params = void 0;
        else if (matchResult.constructor === Object && Object.keys(matchResult).length === 0) params = void 0;
        else if (typeof matchResult === "boolean") params = void 0;
        return {
          route,
          params
        };
      }
    }
    return {};
  }
  /**
  * Define a default handler that's called when no routes explicitly
  * match the incoming request.
  *
  * Each HTTP method (`'GET'`, `'POST'`, etc.) gets its own default handler.
  *
  * Without a default handler, unmatched requests will go against the
  * network as if there were no service worker present.
  *
  * @param handler A callback function that returns a promise resulting in a response.
  * @param method The HTTP method to associate with this default handler. Each method
  * has its own default. Defaults to `'GET'`.
  */
  setDefaultHandler(handler, method = "GET") {
    this._defaultHandlerMap.set(method, normalizeHandler(handler));
  }
  /**
  * If a `Route` throws an error while handling a request, this `handler`
  * will be called and given a chance to provide a response.
  *
  * @param handler A callback function that returns a Promise resulting
  * in a Response.
  */
  setCatchHandler(handler) {
    this._catchHandler = normalizeHandler(handler);
  }
  /**
  * Registers a `RegExp`, string, or function with a caching
  * strategy to the router.
  *
  * @param capture If the capture param is a {@linkcode Route} object, all other arguments will be ignored.
  * @param handler A callback function that returns a promise resulting in a response.
  * This parameter is required if `capture` is not a {@linkcode Route} object.
  * @param method The HTTP method to match the route against. Defaults to `'GET'`.
  * @returns The generated {@linkcode Route} object.
  */
  registerCapture(capture, handler, method) {
    const route = parseRoute(capture, handler, method);
    this.registerRoute(route);
    return route;
  }
  /**
  * Registers a route with the router.
  *
  * @param route The route to register.
  */
  registerRoute(route) {
    if (true) {
      finalAssertExports.isType(route, "object", {
        moduleName: "serwist/legacy",
        className: "Router",
        funcName: "registerRoute",
        paramName: "route"
      });
      finalAssertExports.hasMethod(route, "match", {
        moduleName: "serwist/legacy",
        className: "Router",
        funcName: "registerRoute",
        paramName: "route"
      });
      finalAssertExports.isType(route.handler, "object", {
        moduleName: "serwist/legacy",
        className: "Router",
        funcName: "registerRoute",
        paramName: "route"
      });
      finalAssertExports.hasMethod(route.handler, "handle", {
        moduleName: "serwist/legacy",
        className: "Router",
        funcName: "registerRoute",
        paramName: "route.handler"
      });
      finalAssertExports.isType(route.method, "string", {
        moduleName: "serwist/legacy",
        className: "Router",
        funcName: "registerRoute",
        paramName: "route.method"
      });
    }
    if (!this._routes.has(route.method)) this._routes.set(route.method, []);
    this._routes.get(route.method).push(route);
  }
  /**
  * Unregisters a route from the router.
  *
  * @param route The route to unregister.
  */
  unregisterRoute(route) {
    if (!this._routes.has(route.method)) throw new SerwistError("unregister-route-but-not-found-with-method", { method: route.method });
    const routeIndex = this._routes.get(route.method).indexOf(route);
    if (routeIndex > -1) this._routes.get(route.method).splice(routeIndex, 1);
    else throw new SerwistError("unregister-route-route-not-registered");
  }
};
var defaultRouter;
var getSingletonRouter = () => {
  if (!defaultRouter) {
    defaultRouter = new Router();
    defaultRouter.addFetchListener();
    defaultRouter.addCacheListener();
  }
  return defaultRouter;
};
var registerRoute = (capture, handler, method) => {
  return getSingletonRouter().registerCapture(capture, handler, method);
};
var createHandlerBoundToURL = (url) => {
  return getSingletonPrecacheController().createHandlerBoundToURL(url);
};
var PrecacheFallbackPlugin = class {
  _fallbackUrls;
  _precacheController;
  /**
  * Constructs a new instance with the associated `fallbackUrls`.
  *
  * @param config
  */
  constructor({ fallbackUrls, precacheController }) {
    this._fallbackUrls = fallbackUrls;
    this._precacheController = precacheController || getSingletonPrecacheController();
  }
  /**
  * @returns The precache response for one of the fallback URLs, or `undefined` if
  * nothing satisfies the conditions.
  * @private
  */
  async handlerDidError(param) {
    for (const fallback of this._fallbackUrls) if (typeof fallback === "string") {
      const fallbackResponse = await this._precacheController.matchPrecache(fallback);
      if (fallbackResponse !== void 0) return fallbackResponse;
    } else if (fallback.matcher(param)) {
      const fallbackResponse = await this._precacheController.matchPrecache(fallback.url);
      if (fallbackResponse !== void 0) return fallbackResponse;
    }
  }
};
var fallbacks = ({ precacheController = getSingletonPrecacheController(), router = getSingletonRouter(), runtimeCaching, entries, precacheOptions }) => {
  precacheController.precache(entries);
  router.registerRoute(new PrecacheRoute(precacheController, precacheOptions));
  const fallbackPlugin = new PrecacheFallbackPlugin({ fallbackUrls: entries });
  runtimeCaching.forEach((cacheEntry) => {
    if (cacheEntry.handler instanceof Strategy && !cacheEntry.handler.plugins.some((plugin) => "handlerDidError" in plugin)) cacheEntry.handler.plugins.push(fallbackPlugin);
  });
  return runtimeCaching;
};
var handlePrecaching = ({ precacheController = getSingletonPrecacheController(), router = getSingletonRouter(), precacheEntries, precacheOptions, cleanupOutdatedCaches: cleanupOutdatedCaches$1 = false, navigateFallback, navigateFallbackAllowlist, navigateFallbackDenylist }) => {
  if (!!precacheEntries && precacheEntries.length > 0) {
    precacheController.precache(precacheEntries);
    router.registerRoute(new PrecacheRoute(precacheController, precacheOptions));
    if (cleanupOutdatedCaches$1) cleanupOutdatedCaches();
    if (navigateFallback) router.registerRoute(new NavigationRoute(createHandlerBoundToURL(navigateFallback), {
      allowlist: navigateFallbackAllowlist,
      denylist: navigateFallbackDenylist
    }));
  }
};
var QUEUE_NAME = "serwist-google-analytics";
var MAX_RETENTION_TIME2 = 2880;
var COLLECT_PATHS_REGEX = /^\/(\w+\/)?collect/;
var createOnSyncCallback = (config) => {
  return async ({ queue }) => {
    let entry;
    while (entry = await queue.shiftRequest()) {
      const { request, timestamp } = entry;
      const url = new URL(request.url);
      try {
        const params = request.method === "POST" ? new URLSearchParams(await request.clone().text()) : url.searchParams;
        const originalHitTime = timestamp - (Number(params.get("qt")) || 0);
        const queueTime = Date.now() - originalHitTime;
        params.set("qt", String(queueTime));
        if (config.parameterOverrides) for (const param of Object.keys(config.parameterOverrides)) {
          const value = config.parameterOverrides[param];
          params.set(param, value);
        }
        if (typeof config.hitFilter === "function") config.hitFilter.call(null, params);
        await fetch(new Request(url.origin + url.pathname, {
          body: params.toString(),
          method: "POST",
          mode: "cors",
          credentials: "omit",
          headers: { "Content-Type": "text/plain" }
        }));
        if (true) logger.log(`Request for '${getFriendlyURL(url.href)}' has been replayed`);
      } catch (err) {
        await queue.unshiftRequest(entry);
        if (true) logger.log(`Request for '${getFriendlyURL(url.href)}' failed to replay, putting it back in the queue.`);
        throw err;
      }
    }
    if (true) logger.log("All Google Analytics request successfully replayed; the queue is now empty!");
  };
};
var createCollectRoutes = (bgSyncPlugin) => {
  const match = ({ url }) => url.hostname === "www.google-analytics.com" && COLLECT_PATHS_REGEX.test(url.pathname);
  const handler = new NetworkOnly({ plugins: [bgSyncPlugin] });
  return [new Route(match, handler, "GET"), new Route(match, handler, "POST")];
};
var createAnalyticsJsRoute = (cacheName) => {
  const match = ({ url }) => url.hostname === "www.google-analytics.com" && url.pathname === "/analytics.js";
  return new Route(match, new NetworkFirst({ cacheName }), "GET");
};
var createGtagJsRoute = (cacheName) => {
  const match = ({ url }) => url.hostname === "www.googletagmanager.com" && url.pathname === "/gtag/js";
  return new Route(match, new NetworkFirst({ cacheName }), "GET");
};
var createGtmJsRoute = (cacheName) => {
  const match = ({ url }) => url.hostname === "www.googletagmanager.com" && url.pathname === "/gtm.js";
  return new Route(match, new NetworkFirst({ cacheName }), "GET");
};
var initializeGoogleAnalytics = ({ router = getSingletonRouter(), cacheName, ...options } = {}) => {
  const resolvedCacheName = cacheNames.getGoogleAnalyticsName(cacheName);
  const bgSyncPlugin = new BackgroundSyncPlugin(QUEUE_NAME, {
    maxRetentionTime: MAX_RETENTION_TIME2,
    onSync: createOnSyncCallback(options)
  });
  const routes = [
    createGtmJsRoute(resolvedCacheName),
    createAnalyticsJsRoute(resolvedCacheName),
    createGtagJsRoute(resolvedCacheName),
    ...createCollectRoutes(bgSyncPlugin)
  ];
  for (const route of routes) router.registerRoute(route);
};
var registerRuntimeCaching = (...runtimeCachingList) => {
  for (const entry of runtimeCachingList) registerRoute(entry.matcher, entry.handler, entry.method);
};
var installSerwist = ({ precacheController = getSingletonPrecacheController(), router = getSingletonRouter(), precacheEntries, precacheOptions, cleanupOutdatedCaches: cleanupOutdatedCaches2, navigateFallback, navigateFallbackAllowlist, navigateFallbackDenylist, skipWaiting, importScripts, navigationPreload = false, cacheId, clientsClaim: clientsClaim$1 = false, runtimeCaching, offlineAnalyticsConfig, disableDevLogs: disableDevLogs$1 = false, fallbacks: fallbacks$1 }) => {
  if (!!importScripts && importScripts.length > 0) self.importScripts(...importScripts);
  if (navigationPreload) enableNavigationPreload();
  if (cacheId !== void 0) setCacheNameDetails({ prefix: cacheId });
  if (skipWaiting) self.skipWaiting();
  else self.addEventListener("message", (event) => {
    if (event.data && event.data.type === "SKIP_WAITING") self.skipWaiting();
  });
  if (clientsClaim$1) clientsClaim();
  handlePrecaching({
    precacheController,
    router,
    precacheEntries,
    precacheOptions,
    cleanupOutdatedCaches: cleanupOutdatedCaches2,
    navigateFallback,
    navigateFallbackAllowlist,
    navigateFallbackDenylist
  });
  if (runtimeCaching !== void 0) {
    if (fallbacks$1 !== void 0) runtimeCaching = fallbacks({
      precacheController,
      router,
      runtimeCaching,
      entries: fallbacks$1.entries,
      precacheOptions
    });
    registerRuntimeCaching(...runtimeCaching);
  }
  if (offlineAnalyticsConfig !== void 0) if (typeof offlineAnalyticsConfig === "boolean") offlineAnalyticsConfig && initializeGoogleAnalytics({ router });
  else initializeGoogleAnalytics({
    ...offlineAnalyticsConfig,
    router
  });
  if (disableDevLogs$1) disableDevLogs();
};

// src/lib/web-push/pushTargetUrl.ts
var SETTINGS_PATH_PREFIX = "/settings/";
var RESERVED_APP_SEGMENTS = /* @__PURE__ */ new Set([
  "agents",
  "artifacts",
  "audit",
  "batch-optimization",
  "brain",
  "chat",
  "eval-lab",
  "growth",
  "health",
  "journey",
  "library",
  "mobile",
  "payment",
  "pricing",
  "projects",
  "research",
  "security",
  "settings",
  "skill-optimization",
  "subscription",
  "work",
  "workspace"
]);
function sanitizePushTargetUrl(rawUrl, origin) {
  let parsed;
  try {
    parsed = new URL(rawUrl, origin);
  } catch {
    return "/";
  }
  if (parsed.origin !== origin) {
    return "/";
  }
  const pathname = parsed.pathname;
  if (pathname === "/") {
    return "/";
  }
  if (pathname.startsWith(SETTINGS_PATH_PREFIX)) {
    return `${pathname}${parsed.search}`;
  }
  const segments = pathname.split("/").filter(Boolean);
  if (segments.length === 1 && !RESERVED_APP_SEGMENTS.has(segments[0])) {
    const chatId = segments[0];
    if (chatId.length >= 8 && /^[a-zA-Z0-9_-]+$/.test(chatId)) {
      return `/${chatId}${parsed.search}`;
    }
  }
  return "/";
}
function chatIdFromPushPath(pathname) {
  const segments = pathname.split("/").filter(Boolean);
  if (segments.length !== 1 || RESERVED_APP_SEGMENTS.has(segments[0])) {
    return null;
  }
  const chatId = segments[0];
  if (chatId.length < 8 || !/^[a-zA-Z0-9_-]+$/.test(chatId)) {
    return null;
  }
  return chatId;
}
function resolvePushClientFocusAction(clientUrl, sanitizedTargetUrl, origin) {
  let client;
  let target;
  try {
    client = new URL(clientUrl);
    target = new URL(sanitizedTargetUrl, origin);
  } catch {
    return null;
  }
  if (client.origin !== target.origin || client.pathname !== target.pathname) {
    return null;
  }
  if (client.search === target.search) {
    return "focus";
  }
  return "navigate";
}

// src/app/sw.ts
installSerwist({
  precacheEntries: [{"url":"static/chunks/turbopack-2_14izztnm_wj.js","revision":"33d6aab2104b535cd4e9b1b181292c38"},{"url":"static/chunks/458vpu2k13i5b.js","revision":"52269aa64dbf209980fd356bba959b47"},{"url":"static/chunks/4562ec63evicm.js","revision":"9eac1b566ce798391b2a469ceb1ae2df"},{"url":"static/chunks/452tgu3ao_kqz.js","revision":"a3f7ceb386e63116f32e7095bbf03fd2"},{"url":"static/chunks/451yz98iaovba.js","revision":"3449ebb5b187f820e21a729a40fa02ef"},{"url":"static/chunks/44rtzdkfvi388.js","revision":"9efe3a8519f70ba62c8b973136461a01"},{"url":"static/chunks/44eaaskvauxdd.js","revision":"4bda03aca973da2d7e5bf3b33a3934d5"},{"url":"static/chunks/448t4vi3gos5-.js","revision":"bf53108b073d5d7bcceb61327296ca09"},{"url":"static/chunks/43qosl6mpt1-7.js","revision":"a47394923212c755014ad5cf80123b30"},{"url":"static/chunks/43o9jpw0o5g1x.js","revision":"12c205ba0da39a8f40ff2bb20d9f21b9"},{"url":"static/chunks/43m0d06x_1oqj.js","revision":"b64223dae7c915b68248270d2bf72a59"},{"url":"static/chunks/43k2olyln0x_7.js","revision":"861f9b44976943dee3ceee1a81d68f09"},{"url":"static/chunks/43h07yrsfrd7r.js","revision":"ac79fd719f1b1b78b07efc11c3bc6735"},{"url":"static/chunks/43daexiq-gyct.js","revision":"a6e0ee4f41ba2daedad1e0c0c4b45b82"},{"url":"static/chunks/4316f_ll3vq_y.js","revision":"c62adc510d0bc7ee1184f2eb30ebcf15"},{"url":"static/chunks/42frup8kw8cb1.js","revision":"c3d82f4da0e2b9eff7523dfde6b5c32f"},{"url":"static/chunks/4241s3q4166xb.js","revision":"d31ba9172c56f23cc1e8326bba223cd2"},{"url":"static/chunks/41cmu1c-m1or8.js","revision":"3ad6d1f6f9ea269804d691df098011d0"},{"url":"static/chunks/4155fe4j89a4i.js","revision":"6f1c754058d3ceb985396909fb7a41fa"},{"url":"static/chunks/40xj8y7t7rrtt.js","revision":"d4ddb376cfc3100168ee724bdf7baae2"},{"url":"static/chunks/3z8ombqaogc2g.js","revision":"422d6a2f3715a3a9f13d70fe7fadd47b"},{"url":"static/chunks/3ymkf0k33iwba.js","revision":"2e9f21fa78999881d74d6f6282a79994"},{"url":"static/chunks/3xu9t61zo17hb.js","revision":"ec6225c4c36de9687119162f554bb727"},{"url":"static/chunks/3xfyl8c-x4tq3.js","revision":"2f64df719d36049f97da620241d8e95c"},{"url":"static/chunks/3xatci2h196io.js","revision":"79b49511dff5b43a3b71bb01990ce988"},{"url":"static/chunks/3wn64wa2i5zcy.js","revision":"5ecb1eb704c890befeb10dac395e5703"},{"url":"static/chunks/3wkp4tc7neqad.js","revision":"fce7d023e1cb14517fd79d2aa5ad3c76"},{"url":"static/chunks/3widyljd4rg1o.js","revision":"d8186d58ffcda3efe49514214dc59c5a"},{"url":"static/chunks/3wbjrf6i0b_sr.js","revision":"a2d5badc77212cc984c3035af1d9e259"},{"url":"static/chunks/3w9b3rj1b5e3b.js","revision":"28f66e336cca0f4553ec1e414fc127b5"},{"url":"static/chunks/3w-9edjrujb6n.js","revision":"5bde6f8998e57e0ba0acda00d5b0d329"},{"url":"static/chunks/3v7nhjxralh2u.js","revision":"5d1c25592e2269c432ba216245e25380"},{"url":"static/chunks/3uq4d93b5tdha.js","revision":"076db6b7430f798beca90644b11d38c3"},{"url":"static/chunks/3unzf0btkxlfv.js","revision":"2c99a1d0feff4cd54e109e95fb77ed01"},{"url":"static/chunks/3unu8qff3xyu-.js","revision":"c6401ba42a14a679d9c02fefc291370f"},{"url":"static/chunks/3uhwsfil7dou7.js","revision":"f81a1dafda6a632c33d54f1698892e1d"},{"url":"static/chunks/3ud3na8bxi_nu.js","revision":"283c38de195a5d3ec52beb4fd30f9b71"},{"url":"static/chunks/3ti9q7vmtw3m1.js","revision":"e4a1062cbe7d51db76b2f093c8cc0dbf"},{"url":"static/chunks/3tfvum2w2cc3h.js","revision":"f3bb7a40b1951c2bcbf4b3d790e5c4f0"},{"url":"static/chunks/3tc1jdi_xhvl4.js","revision":"6e6675f9a487d4171cbe59aeaa440525"},{"url":"static/chunks/3t1vrllvwpn9l.js","revision":"9481cc72fc9b661e554573c03ac66952"},{"url":"static/chunks/3t-u_m7mkcdfu.js","revision":"2c807b72ddacd1f69f99f808019ae84a"},{"url":"static/chunks/3sl_6astl6lbx.js","revision":"63db64114ce2451abac027c9f5054547"},{"url":"static/chunks/3s8eca2nl5yc4.js","revision":"0a6bbb25032452060ce5699a23329d5e"},{"url":"static/chunks/3s3t207uusvzw.js","revision":"da5b327fc91d49b1b668f9d070235cbc"},{"url":"static/chunks/3riezlotc3eih.js","revision":"a0dff3a205bd570a3ee16cc5b4f23093"},{"url":"static/chunks/3r55420d4lg81.js","revision":"5d1c343a7e44c1cb13e4d48dea9a46d8"},{"url":"static/chunks/3ppgffk99pd4c.js","revision":"b181d271c2e8a44008393bb7d5b47e98"},{"url":"static/chunks/3ol7pxdvfvbt_.js","revision":"46d106e741d38800d573261d44df19eb"},{"url":"static/chunks/3okmpgkfg98c2.js","revision":"14cc6edaec193115aecbddf5f1b8d953"},{"url":"static/chunks/3ojb3vjljodwa.js","revision":"acea8f2bd7e236d8c802063e7abe9171"},{"url":"static/chunks/3oh32odia7_47.js","revision":"0e643558e798f80eb979d742bdbba53e"},{"url":"static/chunks/3ofly3e5rk41s.js","revision":"392e12ff7383a06644fdbdb591227519"},{"url":"static/chunks/3obrhi7x27hah.js","revision":"cede9c337938fc8246e86130cd17737d"},{"url":"static/chunks/3ndcs_8i3tomf.js","revision":"26fd32855d4407a93505d2b23fda10f0"},{"url":"static/chunks/3mwbfod4iuah8.js","revision":"9b840ab7f0fee9f90bf5f72234a0872f"},{"url":"static/chunks/3mk_zwee3x0tm.js","revision":"558ef1d04ff732d6695bced112942497"},{"url":"static/chunks/3lp7nrt_awpd9.js","revision":"ffe634ebcafb9c2dd2a1daecf79b0c75"},{"url":"static/chunks/3ljz5qioajiui.js","revision":"ec65ebef7f837c125dcaf9a085016384"},{"url":"static/chunks/3libb-12xzgx8.js","revision":"53386c5d4cbf1e7fff0ddecda4b1da1c"},{"url":"static/chunks/3l5ycxxpay_ul.js","revision":"f0cc1f838bb1ba5bbb9282a9e35bcb0c"},{"url":"static/chunks/3kvxuus_9d25f.js","revision":"a47e3134a6d3f791e70a0ac1278feb42"},{"url":"static/chunks/3k_gpjh2kuph9.js","revision":"473da41fc1d6393d1783d459dfe6608b"},{"url":"static/chunks/3jrcpfo7vhxju.js","revision":"dbbe8cef52eb3988a47387e617b6ea40"},{"url":"static/chunks/3j2w5b6flv5dw.js","revision":"588935b5a4d2860d8fe6f0d06cc7fb9e"},{"url":"static/chunks/3iy53i8m9i1p7.js","revision":"d5c18c8b1341c0168b721f8c20c443f2"},{"url":"static/chunks/3ixm82c0d_5h_.js","revision":"4d38e899867e72c1c1862d453de87ee2"},{"url":"static/chunks/3ixl9yg5ir-1a.js","revision":"9fd8ad0a44385851d5de354f0887d79e"},{"url":"static/chunks/3ifotnefrq87e.js","revision":"3989c1b5ea8da7d379123295f59a80a4"},{"url":"static/chunks/3i_xccb5ixg6r.js","revision":"07816325c7a6b4a23b7b98108cecd9b4"},{"url":"static/chunks/3i6lg6c34xpoj.js","revision":"c7385544cf049b740665f8b83d7e2a1a"},{"url":"static/chunks/3i252uyobn-ms.js","revision":"84d82cdd46a6c987d835f87ca1788078"},{"url":"static/chunks/3i1lpdg2_9247.js","revision":"0c53fcd6aba6749de0939857af5971db"},{"url":"static/chunks/3hnu71oic4fmo.js","revision":"f9312430c9cebfd302141263c611da6f"},{"url":"static/chunks/3hknsjyz-ewik.js","revision":"36d4bd990fe289f685f8968dfd1fc7ee"},{"url":"static/chunks/3hk_y08781t2-.js","revision":"c58925967a3f611dd85c4525b9f72167"},{"url":"static/chunks/3hhb_jrkpdsbh.js","revision":"ad41c0cbd8036f587b9d1afb7f67da36"},{"url":"static/chunks/3h4of838im4vm.js","revision":"7c0f031852e2a2867624a749f80c44de"},{"url":"static/chunks/3ggwcn_zw-z4_.js","revision":"9a79d6c40504895c6610c08c224ac828"},{"url":"static/chunks/3g7ng_3waxyhm.js","revision":"de1300dd15af3bb728999721748cf1b6"},{"url":"static/chunks/3fuqv-eey39q0.js","revision":"dd741a7fa77721056f4082b88dbb4c4f"},{"url":"static/chunks/3fd9a1o-va22j.js","revision":"0d028fceb0df136f55053a5e9a3c4b1d"},{"url":"static/chunks/3f37mnrz03dhw.js","revision":"ad35b42edb5d1d166adaad58da6188b1"},{"url":"static/chunks/3f1deb287xo6i.js","revision":"0f1f39cf765edb19d8ee502549f248b0"},{"url":"static/chunks/3etpuucanb1xw.js","revision":"dd78bb09286ab7bef07378390a336586"},{"url":"static/chunks/3er04x8iuypjf.js","revision":"df28179512e76f978e97f810dcb20f66"},{"url":"static/chunks/3elz-u59j91ps.js","revision":"22980ee74df7bc3aa9e3cebfb15805af"},{"url":"static/chunks/3ei2w5uyt_mp6.js","revision":"a7ddef7f0b425d98a4def81478bc0f2d"},{"url":"static/chunks/3edrv9_g8bpuv.js","revision":"6729bc3fcd7a97c3d52c66725349ec4b"},{"url":"static/chunks/3dtekdsxyc8p_.js","revision":"98144f2dcc7ac0b40fb19fffef06512a"},{"url":"static/chunks/3dp02fngyeojw.js","revision":"352fdb5aab0c1fa3ffb717d4db5d5d77"},{"url":"static/chunks/3ddp-t_pmr56w.js","revision":"09a845e0668da01b4b292766087e8880"},{"url":"static/chunks/3cvxz098c3izq.js","revision":"ec525e0cde74bbdedd6d20e4e1fea63d"},{"url":"static/chunks/3csnbs2raeo7y.js","revision":"fc70babfcb6fc25c1c0b3cd0c7097b0d"},{"url":"static/chunks/3crd_04z-41rj.js","revision":"4ad937aa6eed34ee0078d7aef4a98687"},{"url":"static/chunks/3cfsts5jr9jj8.js","revision":"d6d3abc71b695eb1e36143e6b3b64940"},{"url":"static/chunks/3cb6zvgqrbec_.js","revision":"501441d53379d49aa527304e49d482c7"},{"url":"static/chunks/3c0h318sm602k.js","revision":"c4c08285929a7cd482a52aaad62ec98a"},{"url":"static/chunks/3br9zuaadezxw.js","revision":"dd6f0cd4cf4c7aee3ec57cc61c98f500"},{"url":"static/chunks/3b7m5yht0t0o5.js","revision":"db71601e761bd303d15802393d85c52c"},{"url":"static/chunks/3aq5mef6c7l13.js","revision":"25a70c6f12373100309d561fd6f0ab26"},{"url":"static/chunks/3an5polvxnq8u.js","revision":"cc7c6df7ddfcbe5c9469e42fc126676e"},{"url":"static/chunks/3aev97yry10t1.js","revision":"0b28e25864b67dfb0f78ddcf0eb4cf72"},{"url":"static/chunks/3a65-_eoqkn53.js","revision":"b3abde48bd8657be39803d5c29c75882"},{"url":"static/chunks/3a1ul_mj3zrol.js","revision":"5b78c9e4031488e81f5001210cb6967b"},{"url":"static/chunks/3a-936zk6q-en.js","revision":"02c32135687378a1e0a3b0e6273f7a36"},{"url":"static/chunks/3_reaj6xv1grw.js","revision":"41242b4312d74b0d2ed381931bfe4468"},{"url":"static/chunks/3_n3mbayio8fg.js","revision":"a37553a052aa7b1a065d21248122a569"},{"url":"static/chunks/3_l1-k2q2in6j.js","revision":"2cfbf86beafd9c0e570c97466ff82fc1"},{"url":"static/chunks/3_kkgz2xjns_k.js","revision":"083c26352d7a1a5f0492983155d62841"},{"url":"static/chunks/3_da01146v9ns.js","revision":"2f5b1c911d066256ef5fed85a72c3683"},{"url":"static/chunks/3_ayhck8m8efu.js","revision":"c90c872ed4a3ad31532863cfcd1f72e0"},{"url":"static/chunks/3_4j5l_l6j1do.js","revision":"7acb312a101be10e10db65cf1f9662b2"},{"url":"static/chunks/39m8yzzd8e1g3.js","revision":"0047b10833d4b33f98d5c0240e2ed1d7"},{"url":"static/chunks/39h6qij57z199.js","revision":"af286a8647a2a45c0f65cc04df60d60f"},{"url":"static/chunks/398au-dydmlg0.js","revision":"07f9084132f306bdcc9fb8ce04a80e61"},{"url":"static/chunks/38ru5p-4vwqr1.js","revision":"a1069b47963a9132dd38cb029c576774"},{"url":"static/chunks/38hfnwgr8xit2.js","revision":"5631a6c3b39a55967abf9cfb97370d03"},{"url":"static/chunks/380livi8chmsk.js","revision":"344084136d2cd936d41336cca0b2e01f"},{"url":"static/chunks/38-6qxv9g3-54.js","revision":"913d9a5c41b18be6630b3813bf1f756d"},{"url":"static/chunks/37peacemdf-tc.js","revision":"a6e76d9413b340a80daa567bc73fd608"},{"url":"static/chunks/37pb95-aeq2mw.js","revision":"0ed2f9b69944f7cc8c26b597b5a2faa9"},{"url":"static/chunks/37oyfde5ocibv.js","revision":"ed83ec31216de4bcaa480858de6c47a3"},{"url":"static/chunks/37mi6wt1keuig.js","revision":"651b79d2d78011c699a53403816b2168"},{"url":"static/chunks/37mf370t5re35.js","revision":"8a9ba90cfa63666332e4c2e98f7135b2"},{"url":"static/chunks/37jbbd79gm6zb.js","revision":"4cb1adf742994af173d02683465a68c7"},{"url":"static/chunks/37a-35qrt9kxw.js","revision":"0c66815b18190a777c5282a7f22a1ecd"},{"url":"static/chunks/376aevkxzvj9r.js","revision":"74e809313d465adc71d824d44c383355"},{"url":"static/chunks/375kx4u46ch7n.js","revision":"12619520e9ac144b9359bd1313f51b6b"},{"url":"static/chunks/370-frd1wql3y.js","revision":"5809758c6c3d44434a62cb98e18daed0"},{"url":"static/chunks/36r1udzfotwwj.js","revision":"3d3b768ce47d5c2640d9c633f8382c39"},{"url":"static/chunks/368vhupks312x.js","revision":"230a166020369f42405527dbe90cfcd4"},{"url":"static/chunks/35zyivyh_q42t.js","revision":"2baa0b693916deb5bd7b25acdad76da2"},{"url":"static/chunks/35ig2gvwor_97.js","revision":"f78d3253fd910b2d66e087833b31a1de"},{"url":"static/chunks/35az8gm8blhew.js","revision":"6a95ab3d684598f3d89027658cce0c13"},{"url":"static/chunks/34d814e53p_4l.js","revision":"15bf54bd132d92e8a36c9430f0c392d6"},{"url":"static/chunks/347uzffde6em1.js","revision":"ea784a4b62f3cebc6ca4370af86f0450"},{"url":"static/chunks/345vos1i0qty2.js","revision":"d6bfa4a4b97e73b1789865e35cc2c84a"},{"url":"static/chunks/33vajikn5g1cr.js","revision":"5c180f61c4edf8578c6bc6189dddf514"},{"url":"static/chunks/33u67sj2je-jf.js","revision":"6a5716420b5bd8c2fc1c8fc70da7987f"},{"url":"static/chunks/33pztzz16zjr0.js","revision":"903c69714cd3428ba7bfebc24b84594e"},{"url":"static/chunks/33lq_wyrbmka6.js","revision":"0b960104cc4b2d52ea02944b000e7e4d"},{"url":"static/chunks/33f2yw24ozdhr.js","revision":"68f35b38a56a760b3c0eae71496a88cd"},{"url":"static/chunks/32s8ixny0jz7r.js","revision":"420f1524c211e49ae1cec46c38db45db"},{"url":"static/chunks/32cl6qwgz3rjh.js","revision":"c4258374a5fadf6caa84ddd7534931c1"},{"url":"static/chunks/3267re12yq3fh.js","revision":"7b196306e40339def9c5175a3c4e9f86"},{"url":"static/chunks/31u5lo_te8pxb.js","revision":"8020a02337f1053a677756a8335ca5a7"},{"url":"static/chunks/31n0nlf5mclri.js","revision":"381951f86b7f45e7fa31988bd1864564"},{"url":"static/chunks/31k-9-zjzc-wh.js","revision":"3a50ad377fc8331849085b816afadfe1"},{"url":"static/chunks/31js51fn6kqef.js","revision":"e57ae088160fd6c74439da7c4aabe1a9"},{"url":"static/chunks/31a169_a43vd-.js","revision":"c8be0fe427ac0d5b4f5cfd53cbc4f194"},{"url":"static/chunks/30pr-0wuasm66.js","revision":"a932c5bfcebb8a853949530afd66bb37"},{"url":"static/chunks/30iz-yhjkjs6b.js","revision":"9275c3cbb92020e3953861f6ee8734fd"},{"url":"static/chunks/30gnotd0uuh4f.js","revision":"31162d9fe6d3f5f2e5d3e5e61418e5d2"},{"url":"static/chunks/30f--i_zivk7a.js","revision":"404a9192e598290841af0fb4a19b6a74"},{"url":"static/chunks/306wp2i4mndk-.js","revision":"eb13546107cb9a7acd9ed88abc018db1"},{"url":"static/chunks/3-f-lghj18jy2.js","revision":"570d65b8b658e79024731b1318718080"},{"url":"static/chunks/3-9xay3jtokv0.js","revision":"6e52a2949c979bdf0e6d48848ee23acb"},{"url":"static/chunks/2zzfc1xekckni.js","revision":"7b8365942cb6719592e7bfc7e19b95a4"},{"url":"static/chunks/2zcnm8ncwjuc_.js","revision":"c668fe3c3962a36889f21d7fd0469b7e"},{"url":"static/chunks/2z6413htngekb.js","revision":"4c915d6f893c490cc44183cc8044f2a1"},{"url":"static/chunks/2z2fr3d6gcam4.js","revision":"a2da76482d4ad3ffd334ad0124bb7d8c"},{"url":"static/chunks/2ypsnhp3hvt6u.js","revision":"7c5398ba3b62c30ca3b025d32993690c"},{"url":"static/chunks/2y12habnspf5g.js","revision":"26fdf3ec1cf500d2b83a71b64dc6b18c"},{"url":"static/chunks/2y0h8no25ap7l.js","revision":"16c32b07c46ca0b115add83bc6d8d9f3"},{"url":"static/chunks/2y05bhz_i840x.js","revision":"a21edbb36b262bcdf6cb4137f72d3205"},{"url":"static/chunks/2xms7brhmnqv0.js","revision":"947c9b06b656c95bf9be67949a31f645"},{"url":"static/chunks/2x9d9oe18ot5z.js","revision":"f4adf4e9367823ccbeb6497f0e01c752"},{"url":"static/chunks/2x896wbx7at0w.js","revision":"e60903d90f0e412c95e1991c9b7caa0f"},{"url":"static/chunks/2x6fbq8ruzk4t.js","revision":"156a5bf4311b7c09c8e4e4fade084307"},{"url":"static/chunks/2wvrlv3bjq1wt.js","revision":"5b2e2b7d61055a8e61288d31eafa3d08"},{"url":"static/chunks/2wf7tlmald2r_.js","revision":"7d9a4151f3eec5a03438dd5414a01c30"},{"url":"static/chunks/2vaz0ozbfb5om.js","revision":"0fcb11e073c116c1ab465474f12dc06a"},{"url":"static/chunks/2v6_86pm4-7yr.js","revision":"a2c1115038c6db44018baad9010f4516"},{"url":"static/chunks/2v15opjjetdd2.js","revision":"052f9bc703b4c537631496d08ddbe5a5"},{"url":"static/chunks/2uzfhmxo2a8-5.js","revision":"1fd1b5a21a7ec991b15c5fee7257f82b"},{"url":"static/chunks/2uyz23ielzmbe.js","revision":"6c66f2efe590420f5c5fa1223a7679c1"},{"url":"static/chunks/2uv5aw7mt7ix-.js","revision":"a0b842ce41deb55630c943fd745b7c1a"},{"url":"static/chunks/2uqwpdc92t2h6.js","revision":"4fd2abdc2fe43df9cab8490f2d9591a7"},{"url":"static/chunks/2unjykd94tdyd.js","revision":"a0ee8e861773dc20a6a6f25b4690483f"},{"url":"static/chunks/2u701a8decafp.js","revision":"803181fbe2b73b2f1c15f94edef94e58"},{"url":"static/chunks/2u0w0e_05bcyc.js","revision":"98518c58a65c8111d4a1e21437d52c55"},{"url":"static/chunks/2ttr4uno0huqb.js","revision":"4b99b1d0afba7ccae9e5ec5010b17996"},{"url":"static/chunks/2tmhs81t4o2o4.js","revision":"9f9767bcac34dfe5a9dc7cf62b91fa18"},{"url":"static/chunks/2tib2963k206y.js","revision":"b49e2d1cb25122393852923c831f68b5"},{"url":"static/chunks/2t_z2yri8bzns.js","revision":"0f62d76caa67a2cc3f7bf4ebc32c173e"},{"url":"static/chunks/2t78e87plqf5q.js","revision":"04c706be6c357f35aff9632292555550"},{"url":"static/chunks/2t21a22fh6diz.js","revision":"b447a7f9dbf2e75c1bdbe7aac15c4a52"},{"url":"static/chunks/2sr-wpin7f6i3.js","revision":"72d7a7a614b0b89c14dad6afe0da5523"},{"url":"static/chunks/2sblrbdz0wt1h.js","revision":"54059f6cf5e3e4df858b4bd2f2282b68"},{"url":"static/chunks/2rz1r9nups1kt.js","revision":"5303ab000aeb74c368b06f94325a96f5"},{"url":"static/chunks/2rpvn3gv14xke.js","revision":"4010224e60ca41b414b70a76c21d5449"},{"url":"static/chunks/2rkpc493m-4ke.js","revision":"176853903808261e41413e1255cb9202"},{"url":"static/chunks/2rgrtpqjh4mp1.js","revision":"8d49098b466d4727151f4506d5467b17"},{"url":"static/chunks/2qotv8putyu4g.js","revision":"ba79490b16c73eb3b992b78d9cad820a"},{"url":"static/chunks/2q07nfngvfn4o.js","revision":"62fa975fc02b12944e1efd3af5a454ed"},{"url":"static/chunks/2px_r2sxr-5mn.js","revision":"04cb3afe7d6cfeb8ee128259593fc6f6"},{"url":"static/chunks/2ps-6r1c7z38g.js","revision":"efea129d011a4ec9ea2ba0d5b154eac6"},{"url":"static/chunks/2pbr902dvqdq-.js","revision":"cd244bdbb0a2595ad134b20a3409e98d"},{"url":"static/chunks/2ofkgxxepkirr.js","revision":"717db4b3fe3a58199029f99c40247941"},{"url":"static/chunks/2nqzqe5edo26x.js","revision":"a4f2b14616048ee607d0b794bbce717a"},{"url":"static/chunks/2nfnz70k0u4sp.js","revision":"795136c38ee81547b948ee8974cf5f0f"},{"url":"static/chunks/2netrwn_4p7w8.js","revision":"d725fc8bfb1602af6fcd61e7aa8c5df8"},{"url":"static/chunks/2nco-leefbm4z.js","revision":"39fd1bad4908070a071f38b498ef6c6e"},{"url":"static/chunks/2mt76m-kszien.js","revision":"aded539fd1c7790db4893980798a52b2"},{"url":"static/chunks/2mr0j0e9s7q1y.js","revision":"7e165e1c71304147c90b0eb6daa4f0a9"},{"url":"static/chunks/2mq6bx1zhy4_z.js","revision":"1504b20ac92d0d3329f1ae6df4dceaf3"},{"url":"static/chunks/2mjp2zbcf4xd4.js","revision":"afa5ecc6d6ce7e44e98724e6f973446b"},{"url":"static/chunks/2mj2-2lrlzabf.js","revision":"5c5b724bc3229f7728786520b5574eb1"},{"url":"static/chunks/2lw7dqz-x7dba.js","revision":"89ce7d2cee464d4996e293c4d5aee12d"},{"url":"static/chunks/2lvxnm06yamso.js","revision":"67a62ec5cda4a796093c1fbf4ccd0dd8"},{"url":"static/chunks/2lt6wi6ba2e0k.js","revision":"6d5b77da97b39d5b6b9ef76fe321ec7c"},{"url":"static/chunks/2lqyp6sjcse5n.js","revision":"f4b96ea93bb77410576d28b7c30bc198"},{"url":"static/chunks/2ld2cpbqcai1y.js","revision":"c84d232a04d6878d89961fb3d503fcec"},{"url":"static/chunks/2knw3543y_1co.js","revision":"609bac25d764f2ab35b25df54b56800c"},{"url":"static/chunks/2kcivrpeju-bu.js","revision":"b44b4afec65e3bd9175cbbd3ec70b0f4"},{"url":"static/chunks/2k-a4ey0zgqja.js","revision":"8b62f8b80c9bb5d1856e4cefab81bd22"},{"url":"static/chunks/2jk5nx8gaaagp.js","revision":"143d6225f02ef4f479578d701f208e9c"},{"url":"static/chunks/2j5myu26rrr28.js","revision":"5fd575044b348b06a854b0dd986eacd0"},{"url":"static/chunks/2j4v_e0whht8p.js","revision":"f4dda04d98d6c8e4a64efc46ae783398"},{"url":"static/chunks/2j3e5yqnklxyf.js","revision":"af42776d602691c9aa715302a2d94c52"},{"url":"static/chunks/2iufp0ltrm3wu.js","revision":"48e9f7ac3294130db008d330fc42054c"},{"url":"static/chunks/2iqe9rix34l4i.js","revision":"d774f340b7f37bf1a9615b233abfc30c"},{"url":"static/chunks/2ihzvj7wx7tst.js","revision":"ecd1e6235536b7dcde328648a3ab2fea"},{"url":"static/chunks/2i_b70tzm_bvv.js","revision":"55056e309e2b84710ad9447597829c9a"},{"url":"static/chunks/2i802z8pyw-2s.js","revision":"814f72c92bf51a833b4cacda29b3dd9b"},{"url":"static/chunks/2i45gmm8cghr-.js","revision":"fc5c21c0b447eb762a8160f08cbb630b"},{"url":"static/chunks/2hasn_bhn2q39.js","revision":"3183d9876d6adbdddf3971554cc48e39"},{"url":"static/chunks/2h0_k29btfiv2.js","revision":"a4c0c2618ff0b2639e7dffca7344c1ca"},{"url":"static/chunks/2gv-ibh8c51tv.js","revision":"d30107002da19926878ea11d5f7cd486"},{"url":"static/chunks/2gsqiojrhlr6s.js","revision":"ef89bdaef78f17351b548ffeca2227b2"},{"url":"static/chunks/2gaevirgk2zo2.js","revision":"e3c014b02754b34c9009999906954110"},{"url":"static/chunks/2fv44v77r5yk_.js","revision":"09e4c9ac0306db88154995ebd94aad07"},{"url":"static/chunks/2fp_a3ck105pi.js","revision":"fd733e4ccfbb5c8af72d30b096447f3c"},{"url":"static/chunks/2foz_1h-uyxhc.js","revision":"c5edbab1f6b13d4dbcb302a467d6026f"},{"url":"static/chunks/2fb4rrhop1e8j.js","revision":"b3e5a4454071a72838c5f74da1273842"},{"url":"static/chunks/2f2-gpf6wukzf.js","revision":"b6dc502e92bfe3884602c645208573b2"},{"url":"static/chunks/2exbvlz2nkvud.js","revision":"170ca6c294dfe62183b5f09e8ffa8eb1"},{"url":"static/chunks/2ed7a3g_x6b0o.js","revision":"575876710672ec514079077358002393"},{"url":"static/chunks/2e90bva2fs2ry.js","revision":"50b83e4250f5d50c01432420b161d8bb"},{"url":"static/chunks/2duq4j2tj6vei.js","revision":"52cbe4fdfa8f5397ff688e9c17209d46"},{"url":"static/chunks/2dqjxd7bjex39.js","revision":"50a6cf2ed68bca8503e8fc030d4f6f78"},{"url":"static/chunks/2dj9bukx0o1jm.js","revision":"b9009adef107642f9e80804e86b3f507"},{"url":"static/chunks/2dflqcc8kbgbd.js","revision":"6712f0e2d5acf86574071ce7b25becc5"},{"url":"static/chunks/2dagl2a799wor.js","revision":"b0754b71ee7ed4c23a41371587985e03"},{"url":"static/chunks/2d9a68adhyk87.js","revision":"5e1af4ca88d3e79c18d5047f464d4f61"},{"url":"static/chunks/2criljn0gwpej.js","revision":"0d0915c1e8e3eadf816a0ccb1de3423a"},{"url":"static/chunks/2cr8ht-uay8w7.js","revision":"d63209fe10c4c73ce049d66351921380"},{"url":"static/chunks/2c9c2rhq9t0at.js","revision":"b3269e10e0d4fd14194fc1f07f83ad3a"},{"url":"static/chunks/2c64ji3ica8dn.js","revision":"eeaf0ec058f7031db9b4ba0e4ca611a4"},{"url":"static/chunks/2c5bqh1ttzk_l.js","revision":"12b638387d408ddf2fa760a154071af6"},{"url":"static/chunks/2c43ak78b4aq8.js","revision":"03bc7ab32bddaa2e7ed215bb301fccb9"},{"url":"static/chunks/2bwijmnwxq8zk.js","revision":"fa5fb3a74ece951bd4fb9aa595840524"},{"url":"static/chunks/2bsjgoysa59a_.js","revision":"6a5af909e4db84d404a2fa5a3b9d3826"},{"url":"static/chunks/2bnr7v8q1__57.js","revision":"b32d8c5b87f7ad46d0f03580e3e40df7"},{"url":"static/chunks/2bn3u3q52i4u3.js","revision":"cdefaf9f646b1005e298ee45329fd1d1"},{"url":"static/chunks/2bcl3n-6efh-0.js","revision":"2cef1aa424b0ba7fedb982c639ee2e7a"},{"url":"static/chunks/2bborlwwpxisy.js","revision":"7da9f0cd86473ac317e1e6850b5d38b2"},{"url":"static/chunks/2bar6sjguuvg1.js","revision":"ebc343887a3cbe00afbd5b9d0143d6bc"},{"url":"static/chunks/2b_wef6w_1ifw.js","revision":"8de6739753f45b2c967b665d18cd499f"},{"url":"static/chunks/2b-e81g9zl46-.js","revision":"c14f16e71977053ea4144921bc10709f"},{"url":"static/chunks/2azthvl_i-f1o.js","revision":"cfc4f316f9856ac06bfb414b8974e2e0"},{"url":"static/chunks/2aynf3mx6yfwj.js","revision":"82aaaa557185b7e1ae85dc4f83fe1eb8"},{"url":"static/chunks/2auziyl_ebbhk.js","revision":"403cc9ea68a5c86e88e0cfcab97849ed"},{"url":"static/chunks/2atjtgk-b7uvz.js","revision":"a8dc237efb7cea883bac2c98e43a5371"},{"url":"static/chunks/2as6p-jgdzp6k.js","revision":"54311af39576123f7186455ad71f2699"},{"url":"static/chunks/2arxh_71n4t1a.js","revision":"e326eae8fd8612e0fbf15f536bcb1b0d"},{"url":"static/chunks/2alk1r94-pbu2.js","revision":"8883550ba97f8533fa7132b3d195868a"},{"url":"static/chunks/2adf79al4an23.js","revision":"3d21761e5bf80aaa8e364f9eccb76876"},{"url":"static/chunks/2_lxfalvobwpp.js","revision":"9ebdc3925fd42ba6da148c65c62aad5f"},{"url":"static/chunks/2_9nadm66x7am.js","revision":"dad58b2fe10249d2fba5421f07220395"},{"url":"static/chunks/2_69dil0-8wdu.js","revision":"eb9abc7167a2ba56bc0a5f4ff99a1c8d"},{"url":"static/chunks/29ju69hg43anb.js","revision":"01dc0f63a58278d4056ae33908b5004c"},{"url":"static/chunks/291c8zvy2bljj.js","revision":"ed43362a6e9573f8cddad68cf9253278"},{"url":"static/chunks/28tpiqf-j5tkb.js","revision":"100ee710c1b2c67221d14ba2da3a1ca4"},{"url":"static/chunks/28mi352g2zs_z.js","revision":"6ee7d6a3d3c9654e81b679b27cca8809"},{"url":"static/chunks/28lm4i1se5rek.js","revision":"62b469d77c0205060986de6fb2703106"},{"url":"static/chunks/28e2mutifmnx3.js","revision":"9bee4e094a618786b8ceeaa10a7f4fd5"},{"url":"static/chunks/28cj1echdi149.js","revision":"42c87e0bddccda430ba6910c5559eb47"},{"url":"static/chunks/286_yzrqq1f30.js","revision":"7e3e88d0e72fa6fb2ee14208587dbffd"},{"url":"static/chunks/2807811pk7b5i.js","revision":"af92e246ab1e005d5085a5c439f51301"},{"url":"static/chunks/27umho2_01v1_.js","revision":"fa9d2f17ce098248e5bad7ffcd9d8929"},{"url":"static/chunks/27r3oxu9stj10.js","revision":"9090b22cff15164b0d27450ed7b463a8"},{"url":"static/chunks/27nxw3qam16i-.js","revision":"ca35ade2a384db6e4210c01e329a95fa"},{"url":"static/chunks/270po6bayzpt7.js","revision":"9788de099a49cd1bd4498a5469b7cf17"},{"url":"static/chunks/26afu5gj8t900.js","revision":"f127ceebcfa656abec0aaf87b1a46dbc"},{"url":"static/chunks/264xhwccyzk09.js","revision":"4336b079de6efcde8b81c76f51ab2726"},{"url":"static/chunks/25y_y_3lctkh0.js","revision":"935adbe09c25424ae5d80c74adfe7098"},{"url":"static/chunks/2538wccgzz6z3.js","revision":"a40a4bee7dc7f54608f30640a238494d"},{"url":"static/chunks/24ef0gjcx7wie.js","revision":"c1d62ae92dd100b5f709af21a8f664b9"},{"url":"static/chunks/23ve0cjsq66k8.js","revision":"0f7445e52dd4eb00f5deaf47f6c833b8"},{"url":"static/chunks/23tau0nsyxznx.js","revision":"9b3cb3e51a8c355b78bd593f183aa484"},{"url":"static/chunks/23qf6f4-2pcf8.js","revision":"edcf93633639476a8d155e729e04e82b"},{"url":"static/chunks/23npu6qo3c-zh.js","revision":"c825eb1a35896664edc9f0105caace78"},{"url":"static/chunks/23n0fozse9few.js","revision":"4d946a5787800da942d9259271503d96"},{"url":"static/chunks/23hte62zmksu-.js","revision":"16acf7c2a093b956a4269326e815e20f"},{"url":"static/chunks/23d1nx0j-bo1y.js","revision":"caf153245bf425e65baa419ecc3c3d07"},{"url":"static/chunks/238778hugukw4.js","revision":"63d393a1b7e2307eb901144a08defbde"},{"url":"static/chunks/230oy70gyp6vi.js","revision":"490808b0ca762bbb7bb85d4e6d094f01"},{"url":"static/chunks/230a-vqw0--fq.js","revision":"3b90af89d48daf4740b9581e67b2bf1f"},{"url":"static/chunks/22pn2gewr97dr.js","revision":"eb53374e6e0684fe9061b51dd145c1b2"},{"url":"static/chunks/22migbq45mop9.js","revision":"3c03dbb895aa7ce5e52b60a1c85af1fd"},{"url":"static/chunks/22b-bx40xrfht.js","revision":"8d5a514fc214793723405efd170c248d"},{"url":"static/chunks/226xsywfv21id.js","revision":"a15bd25f082da7a81a9ad7d66eb8711d"},{"url":"static/chunks/2214vyyaw4ewr.js","revision":"ca8f56a6a2ef7ec6792f9f1bd5547f44"},{"url":"static/chunks/218hq6c97kvj1.js","revision":"42c434099a47a2a50d305663b289f9e6"},{"url":"static/chunks/20af7m-r39z49.js","revision":"1799347c85a23b7a4d09f87b3d74b194"},{"url":"static/chunks/203ytfs94_fda.js","revision":"92b7a17b29155dbd4a54685d5c550f2d"},{"url":"static/chunks/2-u76n269oqm8.js","revision":"bd0c8e6f5dbb86ff47d01a3fefdfb152"},{"url":"static/chunks/2-plc2uyjaz-l.js","revision":"abf9cb053e849a811121641e92edb9c5"},{"url":"static/chunks/2-m88l587ow84.js","revision":"be9ba9d6f1d9fb0be6d34432c7d314d3"},{"url":"static/chunks/2-0ni6k_xb-12.js","revision":"538565a3c677ecbd8715b0e4ea458bbf"},{"url":"static/chunks/1yk0l4tfxjzbt.js","revision":"eca1a2f2c387aed424d44c9a4b6171ae"},{"url":"static/chunks/1y1gi8gp1s0ak.js","revision":"d137be52caa6c0f6db20d604b8fde24e"},{"url":"static/chunks/1y10dkbohhg1h.js","revision":"ad2757f091f206e2f6e0cfc80eaf8328"},{"url":"static/chunks/1y0vp-7h9f38q.js","revision":"14a38b7bb3e7340ab4edd141190c8a15"},{"url":"static/chunks/1xumay126j4nr.js","revision":"4c9a9b560c3fc354cd23fd19c41cd7fc"},{"url":"static/chunks/1xsdrjcgxddix.js","revision":"97d8d29361a7512f49197a41f41abfd7"},{"url":"static/chunks/1xpwsg7faif82.js","revision":"9e1016edf96d9d3bc08b6be5f15c8b00"},{"url":"static/chunks/1xi741diggtcf.js","revision":"e41ae92adabc291e83e39f5dda9b746d"},{"url":"static/chunks/1xdp4galzwqw1.js","revision":"f46f88a47d1a7d078d54b01e05de027c"},{"url":"static/chunks/1x7wm1adeivqz.js","revision":"1ba4d4aa34d9040f9978b7fc09d400e6"},{"url":"static/chunks/1ww44dn8zd42_.js","revision":"f12312400fd302c821cb0ac35816c803"},{"url":"static/chunks/1wsfum4qf9upr.js","revision":"031862c73981b6a7afaa955c16d28fb2"},{"url":"static/chunks/1w4jstof-de_c.js","revision":"65f46c3081bb658439a87eaa1bb383ed"},{"url":"static/chunks/1vho24__txaql.js","revision":"95d4acf8b67b337b54c31f3162744c94"},{"url":"static/chunks/1v-lmy-bh6-2e.js","revision":"54bfdd39bb9e4d3d156d7f17367d9822"},{"url":"static/chunks/1upijwlozqt37.js","revision":"1bf876e5663e8e955da6fdd75665c007"},{"url":"static/chunks/1uieywbln6587.js","revision":"6bbb41c344b7129852580cf7b18aa0a4"},{"url":"static/chunks/1tquq61sg0o1r.js","revision":"236d0825f84ee8ef6b563661706750ee"},{"url":"static/chunks/1tf77ownh9dah.js","revision":"9a87fa48a0ca80d74447dddd7bd9336b"},{"url":"static/chunks/1tcs-0pzppjd5.js","revision":"e736052e1e181afbe8754cbe23e294ca"},{"url":"static/chunks/1ta8krxaffs9h.js","revision":"cc1dca5092439cb8d2cc639afe8c9d2c"},{"url":"static/chunks/1t-n59322ypjc.js","revision":"cecf2f0257d384d80fa8c732d04a82cd"},{"url":"static/chunks/1syii-4yuax-h.js","revision":"522cf00601e342900a11010bac5786bb"},{"url":"static/chunks/1sq_1vgc2jbhc.js","revision":"a7d736bf149201f555329cd7a67cf4be"},{"url":"static/chunks/1scwa285ycnil.js","revision":"93bec19a30e554580d5d6637ef9a8773"},{"url":"static/chunks/1s335pm5wl917.js","revision":"bc7a27533cc84674685197b9b6ee6977"},{"url":"static/chunks/1s2iy80yf5a44.js","revision":"f06e25b0b91b2b954610e6e6dd7bc3de"},{"url":"static/chunks/1s0h2i3h4fxns.js","revision":"f06ec28775ec9c41cb1ebaa0ee763149"},{"url":"static/chunks/1s0gocagrv75w.js","revision":"07de0474c70901705fb9888b38d5aed8"},{"url":"static/chunks/1rycb2ts16jhf.js","revision":"7c46979c7b3a9f7b724e53beb3238e88"},{"url":"static/chunks/1riwkanjy4gt-.js","revision":"3e8f1b30107de909ae51c3c06a1ea59b"},{"url":"static/chunks/1r04x1dhph3vp.js","revision":"be5476a9b2dd7123745face3d1be5396"},{"url":"static/chunks/1r-kq12s69b29.js","revision":"77eb2817e525c94b93d460b16ec63f27"},{"url":"static/chunks/1qz2_gehaj2d6.js","revision":"04111be47d50295fc55921862cf7f535"},{"url":"static/chunks/1qbu2lkw9i28b.js","revision":"26b110e7be416658e5336df750e03cc5"},{"url":"static/chunks/1pwtttfenmgb2.js","revision":"d94ce2e8ef534be135aeea4e3ffa9022"},{"url":"static/chunks/1oqkeqs1am_2t.js","revision":"367946ea705f7cf51fcca319c315d5e5"},{"url":"static/chunks/1oh_0haontmd4.js","revision":"b472e37b95a2292cb19d02ab20e82ed2"},{"url":"static/chunks/1ob6xzezv33r8.js","revision":"c9ed9564ec036c113ca6fa01e5dee3c5"},{"url":"static/chunks/1o6gahapv-570.js","revision":"c2c8c743465e5fd67b80c733cf411e3e"},{"url":"static/chunks/1o12y_vxihv7-.js","revision":"a21ce5d6234d4810e1a9802445423486"},{"url":"static/chunks/1nrf2tp5vrryy.js","revision":"f6c6369b94de5331f3e698d9568031bd"},{"url":"static/chunks/1nimf2yy5yxrm.js","revision":"7cd548701b180ca50fbef4e1ac8e8a28"},{"url":"static/chunks/1ndut5s5q9uu6.js","revision":"aff7d03b4bfe8f936a2d06c05b5b3463"},{"url":"static/chunks/1nc_5lueo7a4h.js","revision":"b8eba523cbbe701a3596b138520ac9df"},{"url":"static/chunks/1n_ynj-q8t37a.js","revision":"f4e74529cb663fd898e3f91f2c062389"},{"url":"static/chunks/1mfuzexom6if6.js","revision":"5b2651c90711bdc89634e382b7dcf239"},{"url":"static/chunks/1m4sxbivvd99q.js","revision":"b537325d0324b3883208faf392f7c557"},{"url":"static/chunks/1m1i7ybec589w.js","revision":"c05ab6aa3a0d38d70df727537fd63d21"},{"url":"static/chunks/1m-_gdfilnemg.js","revision":"967878e9656b9f040a4837d9afb41a9a"},{"url":"static/chunks/1ls_08eln4hmh.js","revision":"ebafb7814f0086ad2a10f245afd88bce"},{"url":"static/chunks/1lnducys3zm9e.js","revision":"4c9618e1b6574e428d80ed72a821849e"},{"url":"static/chunks/1lmtv8t9vgf1i.js","revision":"586257a54610a357cb5752733278bd7c"},{"url":"static/chunks/1l35a49okuqxn.js","revision":"b94a3698ad9c37df786ea0d9538d2b73"},{"url":"static/chunks/1kji_ngxz_ngj.js","revision":"928a64df7f9a414e69228f6d9ed1f3cf"},{"url":"static/chunks/1kba9ynizoz0y.js","revision":"2fda49261255959839716324ed45b782"},{"url":"static/chunks/1k6b020piju4k.js","revision":"58da90be8b74984058bb49f452ec97bf"},{"url":"static/chunks/1jaooa86w-p1_.js","revision":"05d33098238b88277c979470f61f5cbf"},{"url":"static/chunks/1j88qhkwmcu47.js","revision":"3100267c343954c88fa6d417c67ca7e8"},{"url":"static/chunks/1j36smshfknvt.js","revision":"4b66af40b34ae22597851177b0ae89fd"},{"url":"static/chunks/1ira4hn98lvby.js","revision":"0dd11f67c2ce08630049989d4857b270"},{"url":"static/chunks/1insz1e1_isnl.js","revision":"d00cb0fbcdee19e884cb5f2785b1566b"},{"url":"static/chunks/1id8--t0vgn5f.js","revision":"1468589b14094f02afaaa1272902d97b"},{"url":"static/chunks/1i132ftx95eyz.js","revision":"09bc68021a13db36d60465e3b9ae3fa3"},{"url":"static/chunks/1hk281o2m3zsj.js","revision":"498b13789b0a1aaff2ada94d6383046c"},{"url":"static/chunks/1ha3z69q-c-_s.js","revision":"b4754c800f0fdc8e24e0620afe43c50a"},{"url":"static/chunks/1gzext4ds7thc.js","revision":"008091c7771e5cb4b181a2f095014d76"},{"url":"static/chunks/1gnstdad32msy.js","revision":"291032f0ae239b949b6ab296560e5ab5"},{"url":"static/chunks/1g5rwc_2par46.js","revision":"7a5534bf4a454daed4725b0ae7d698f0"},{"url":"static/chunks/1flixidvj0din.js","revision":"cd2eb303d6e4b8fc4ed914ba583648a3"},{"url":"static/chunks/1ey3o912wq99b.js","revision":"018b723937902cb902d76658ef023c03"},{"url":"static/chunks/1etybc8uk1vbb.js","revision":"c6d0073eb59ac872ed3bb07f849d0c81"},{"url":"static/chunks/1et52gye2l0lf.js","revision":"a110d3a4bbc9eb1e8642c3ae48ef61bd"},{"url":"static/chunks/1eqpl8dqci3jq.js","revision":"e3b635395d5aa205c4133979cde48e32"},{"url":"static/chunks/1ehskhz9ak_ep.js","revision":"5b255ce76083ad8016c31e68a5aa3bc2"},{"url":"static/chunks/1egopb_mjqrii.js","revision":"8a9ca0ec55e8cf0668e45c68bc23fe71"},{"url":"static/chunks/1eawk23dlxu2j.js","revision":"79aaafd875ed48f8343bec9ed766fb7f"},{"url":"static/chunks/1dqbu69c4pi3y.js","revision":"38438aca7295375c971f35ea33bf4222"},{"url":"static/chunks/1d2a7u9dlbk3n.js","revision":"46b00d97751f917b2875a0dc39cbcd09"},{"url":"static/chunks/1d1yvsupjs1wn.js","revision":"eb6bdbc3d268dbffa64cc6592e0cc893"},{"url":"static/chunks/1cxecp3pjwk9r.js","revision":"fb63dc3d43159256f922d2a82323bb4e"},{"url":"static/chunks/1cr31k7xr57jj.js","revision":"60c4d8f29693a99778275499a1dcaff5"},{"url":"static/chunks/1cr1-f4hu3vu3.js","revision":"0237c8bf4b12f18cdb683fcdd4d375cc"},{"url":"static/chunks/1cf9f-13uyam0.js","revision":"db718838c62665e2e9c6786ae16b97f7"},{"url":"static/chunks/1c2g-i40ebvxk.js","revision":"15042e819fe60db95d45f94c2979db6a"},{"url":"static/chunks/1bosjc1zop-_a.js","revision":"671834b51cc5811c8bccc9e38ed84613"},{"url":"static/chunks/1bkoyzb_hzm6t.js","revision":"6373af4d2f57217c7a236a800792fe52"},{"url":"static/chunks/1bg30mn4mb8hb.js","revision":"6480f890a844dc5a7c68b9fd61aac6cb"},{"url":"static/chunks/1b6hrc66k6npe.js","revision":"606086ea439ff4cbb3a7508af5164082"},{"url":"static/chunks/1az1d241i5fx-.js","revision":"94d9c4a73e8b73e076ef877b0cde3fc0"},{"url":"static/chunks/1andkiq_k0slz.js","revision":"c048c5bd982133e98e488dec3fadcb2a"},{"url":"static/chunks/1abyfc9kvkm7q.js","revision":"8a6c64fd3948ea484ca0a97f309160b6"},{"url":"static/chunks/1a4h_df1exul_.js","revision":"fc7c39f56fd3e701febbf9a43be62fc7"},{"url":"static/chunks/1_yub9yu32-8e.js","revision":"11b87ea080554b694f25b315aea6dc5c"},{"url":"static/chunks/1_o73lu7rmmgx.js","revision":"560dae21cc74fbf352b15ae49c44ee18"},{"url":"static/chunks/1_j6utejizqbs.js","revision":"30099c2a6fb81b3f3f7edb32d924a247"},{"url":"static/chunks/1_94y5mbbr8-l.js","revision":"fa7f720d5ba1ed6893053d459b20c0b9"},{"url":"static/chunks/19lddr39e7p8g.js","revision":"98cd0b284c9ce16205ed642de5184f06"},{"url":"static/chunks/19fjio294xdam.js","revision":"f71da89c4381c8731772ffb5c7cb831b"},{"url":"static/chunks/19ddl9wbkz5x3.js","revision":"f86aa21e4aa9d8840a506883d8a42755"},{"url":"static/chunks/19ba_iwp2ku8c.js","revision":"42d6d817bb8c729f2baafb25f2373363"},{"url":"static/chunks/18m5wmv9y6zz-.js","revision":"f42f0aeeab72c2479c82cfd99146b72e"},{"url":"static/chunks/18gytbpx0b1u6.js","revision":"29dfebf29d8db06e0b15588a529f8465"},{"url":"static/chunks/189a9y3bshkqe.js","revision":"718df491c0ff86c573b8db37552063e3"},{"url":"static/chunks/186qayy5yosb1.js","revision":"7e7d3c9acc94fd3dbb4c45d346d45932"},{"url":"static/chunks/185ugu44wc2ps.js","revision":"7c92bddc5f0e5c7966fece4fabf37b5e"},{"url":"static/chunks/184wx8veqvpmp.js","revision":"29da79c99793279281437e0aaa064881"},{"url":"static/chunks/183do55tgt_b8.js","revision":"8cc5290a9382dc73757d1d5c71f94afe"},{"url":"static/chunks/181d29m6rjk8_.js","revision":"d4e4274cc609dce7504c3d9020f9dafe"},{"url":"static/chunks/17p5bpr4jq6nq.js","revision":"e39f55ded8024eb81402119417a3868b"},{"url":"static/chunks/17janvhea26d5.js","revision":"c83255201ed5454da2b2254d9af03875"},{"url":"static/chunks/17bx31aeszt_p.js","revision":"9720c35d4ad65afeec4510a277aab6fd"},{"url":"static/chunks/171mnjjwozm67.js","revision":"8d5e457d8541a9200bc9521227ab9f73"},{"url":"static/chunks/16sx5df_2qm55.js","revision":"a4512e84532c960f6884e78d4d22c2bf"},{"url":"static/chunks/168p385jcqmba.js","revision":"1b0ea5b0f3b3b3d76fcfb22e973773ce"},{"url":"static/chunks/167o9xz2k538f.js","revision":"39521c90aab3fd2f7fca5be73e439783"},{"url":"static/chunks/16-nt6wtrza_e.js","revision":"ab13d12557267775ef6f63198a57af2d"},{"url":"static/chunks/15k6t06bl9en3.js","revision":"2bed9594b28433cbafafd5c3caaf4a58"},{"url":"static/chunks/14w5q2en0o2fw.js","revision":"355622cb9aff803bd365a4ed749f82fa"},{"url":"static/chunks/14qp5edd_rdht.js","revision":"99ecb9d92f87150e73d731c69a8d449a"},{"url":"static/chunks/14llia-bfdmcv.js","revision":"f0c52f1264518bf2874e53e9841c253f"},{"url":"static/chunks/142sf79-nnr32.js","revision":"d8d50d94cb5351d800c78ef1d5e7380c"},{"url":"static/chunks/13nfgeax9_qps.js","revision":"be7cf9787e76a0558630b1f8e3a08152"},{"url":"static/chunks/13gi9c2p9goqh.js","revision":"181e0472c9c0a728429990c5f50011d2"},{"url":"static/chunks/13btkpvgxh3bl.js","revision":"d8f6d33b2bdd3a5dfd5067ef12e14c70"},{"url":"static/chunks/12zc6u223h_uz.js","revision":"a93dfe42ea19d03d7f5f421dcca2a619"},{"url":"static/chunks/12x-1ugk-akb3.js","revision":"e942518cd87d9aab6d02dcdc5a323857"},{"url":"static/chunks/124d8ve5gf5t5.js","revision":"78d31d4023c110b8f0e2c9bce344a4fe"},{"url":"static/chunks/124bxoa1bx_1s.js","revision":"25429ee9ad484ada87a25a913a637a4a"},{"url":"static/chunks/11mw6se1a3a1b.js","revision":"3fdebc5b7bbca352f69143ad861802d0"},{"url":"static/chunks/11j-mlfcdscz0.js","revision":"baccd9940863ff372e4898073e705ead"},{"url":"static/chunks/11e-yglsu7odg.js","revision":"ca8125338c7f6fefa6fccb66bf316b5e"},{"url":"static/chunks/11_4yeass7tb5.js","revision":"11b27d6729ebbe01ddd4a7199224673a"},{"url":"static/chunks/110x5es9nbczc.js","revision":"a0632586cdd284f003084a8351d37ea6"},{"url":"static/chunks/10s0c88vo_cke.js","revision":"9186d681fe52359ad43beae7244d4bcc"},{"url":"static/chunks/10f865k043sq2.js","revision":"cc98f09ae3f6568ce0a1f3f88c564ab8"},{"url":"static/chunks/10306el4bi1gd.js","revision":"9e8c1dd71de31441be2a8b47bac428b9"},{"url":"static/chunks/1-ymufwrednwn.js","revision":"16165c6d0190a13eec8fdd56b4c16ced"},{"url":"static/chunks/1-s0p8df2txn9.js","revision":"d9a785939837a6f66ff8c1511393dd8b"},{"url":"static/chunks/1-f26juzswr0r.js","revision":"bd9ae36f35c007aae8acd4ff250036bf"},{"url":"static/chunks/1-dnn2hw3fy_i.js","revision":"f64b379779f31874243753dad2dc7363"},{"url":"static/chunks/0z71y_talj7ck.js","revision":"5dd5a55d043072483c6b99c2fef33834"},{"url":"static/chunks/0yn14fu0eub_l.js","revision":"8152fa3ec71f4b6340c0cf7db624e3ec"},{"url":"static/chunks/0y-0pju86k2pd.js","revision":"23639d4a7dcc9a757559d19784fbab3f"},{"url":"static/chunks/0xn47z7z857cw.js","revision":"004213712b6b6591de1032029b26931b"},{"url":"static/chunks/0xmlxv5spc-7f.js","revision":"8647250592ede0d0b9e71103d63b0c1f"},{"url":"static/chunks/0x4dd1fk94t0q.js","revision":"0648929d99e1d5d0b61b2da2b68422c9"},{"url":"static/chunks/0x4_udjyx_6z-.js","revision":"77a3ce5ee76349231ca82a3cf4992f18"},{"url":"static/chunks/0wpz8sncpt2_5.js","revision":"bb4439be886b34269cd357b102f8708c"},{"url":"static/chunks/0w4vzh83o7uet.js","revision":"c7c558a136e42769c4a1d2c8cbc60b49"},{"url":"static/chunks/0vhbca7uupb34.js","revision":"9355066f552d05662031735edaa46ab0"},{"url":"static/chunks/0v7bgafl-2qs5.js","revision":"20c593f002374fef651fe24fee84e705"},{"url":"static/chunks/0u4wq1qx7o16k.js","revision":"fa3362d56fe5ed7a804d3dde65880245"},{"url":"static/chunks/0tpjzow3z69ex.js","revision":"1062295c8ab4a03f492773ddc7e0bd79"},{"url":"static/chunks/0tm7q5ggu3qic.js","revision":"7dbb1a901c873fef93068daf2f1430a6"},{"url":"static/chunks/0th90cn8jdoee.js","revision":"6ef6207d6104ca755050dbf3cb394c85"},{"url":"static/chunks/0t5v98zz9m8uu.js","revision":"7e646f848d9b7ba3453ae59071398390"},{"url":"static/chunks/0sph_z586bvvz.js","revision":"dd61559ddd55b5b3833a55edbe9cbdaf"},{"url":"static/chunks/0sf27qt46cf54.js","revision":"4c6a8344c018886c71455ef312000b55"},{"url":"static/chunks/0s1zhfko2ue8x.js","revision":"ee8c35ec2792f40dfd80d2bf524610ba"},{"url":"static/chunks/0s00zeyhrhhpq.js","revision":"1aa49c70ea7a9eef7020e420dcad9db7"},{"url":"static/chunks/0rptgfnqekwzh.js","revision":"6a73f9765b8c17a6f72be2aae4350b03"},{"url":"static/chunks/0qp50tm70m579.js","revision":"633e6a87d8bd5dff4892d0e741a00e70"},{"url":"static/chunks/0ql2j7ml29q9o.js","revision":"792096349750676c71e00b2229128453"},{"url":"static/chunks/0q6iluaupmx1t.js","revision":"0b21c5e5c99a9c163e3e238e1f04e492"},{"url":"static/chunks/0psrtf2kvb6h6.js","revision":"0c9c977b8ea33ebb1664df03b504acab"},{"url":"static/chunks/0prfv0tf5icn3.js","revision":"db9a360e3e9550d8232378529ee623a7"},{"url":"static/chunks/0phdq2yymzvx7.js","revision":"c59d45ca4267348bae03b8b85e7df9bf"},{"url":"static/chunks/0pculdi1wbbiz.js","revision":"6e981f2cda744e73dbc373d524634691"},{"url":"static/chunks/0ox8v9veo_u9k.js","revision":"deb914ce1ccf6642eaf52c5c3aeac680"},{"url":"static/chunks/0orw2pea_lfq-.js","revision":"c30a2e0b76354461472f3893715df6e7"},{"url":"static/chunks/0ooe3mb8-fwmj.js","revision":"8903d6f7e8c5d666fb5b98d6616c3ff4"},{"url":"static/chunks/0ohmmyw4ykrxt.js","revision":"b75cd608015a6a934a3ecaa0a9a3b55f"},{"url":"static/chunks/0od99c_6sx7r-.js","revision":"40017094323aa53c0e15a665c21dc81b"},{"url":"static/chunks/0o0jgntpj7lcy.js","revision":"415aa6a7b43e59d478cc1aa041ed49c8"},{"url":"static/chunks/0nwp529_4ua-q.js","revision":"85b83aab11e503f8e9f3661c0bf51441"},{"url":"static/chunks/0nqqbr225hd8r.js","revision":"7635b0168a0553bdfc815237033b00cf"},{"url":"static/chunks/0nh4hj_xxjdsw.js","revision":"93dec19eb865d7b6a1eb8cdd92c102b1"},{"url":"static/chunks/0mux_nk6qn3ly.js","revision":"07031630b6adf42a6f6c6249a9528fa3"},{"url":"static/chunks/0muun42nmjdgi.js","revision":"a3e63b69206f57c3129615d76221ba9f"},{"url":"static/chunks/0muq7zqoe64_r.js","revision":"d56a307dde505c767f336fb07312b9c7"},{"url":"static/chunks/0m-l77f8pxn1m.js","revision":"159f378fe97e80d1884ca95a8a69c481"},{"url":"static/chunks/0lsus1maqqzsh.js","revision":"1a5812ae319b9303643281d922e46a2a"},{"url":"static/chunks/0lgo9yxjq6x7y.js","revision":"fd65423141282cd63a6e6bc4aee83e48"},{"url":"static/chunks/0l7o219t84n08.js","revision":"97fefa139512c27446b5df6fbb396d49"},{"url":"static/chunks/0kxhfd9ric8tu.js","revision":"22e538f0c022a277b40217e40fead69c"},{"url":"static/chunks/0kua4guie81cj.js","revision":"13515b1fe47a046c68e9e59380180644"},{"url":"static/chunks/0kf1vwcd_963g.js","revision":"dbf1407350f90f16785e6c25a460c54d"},{"url":"static/chunks/0kdcc6n6woios.js","revision":"409a574be5b458a75b1ba1adae8a6aa9"},{"url":"static/chunks/0kcdxwan9dv66.js","revision":"512fd1a0943f420d4594286ba87feba2"},{"url":"static/chunks/0k93kekw_7yk_.js","revision":"587b884d18263934199547eac7f99559"},{"url":"static/chunks/0k863paltv-uc.js","revision":"f76ecd33224afe0238793017e26f8908"},{"url":"static/chunks/0jr62hnm1ruu1.js","revision":"ee0ceb4728bd64cfbcc3c8d7229bd167"},{"url":"static/chunks/0jql_6uc8_ss4.js","revision":"21413bd231636f70d392b1ffab02a944"},{"url":"static/chunks/0jlm1vai93q92.js","revision":"33869e94b6d8ac9d5cbf65a38a7216f9"},{"url":"static/chunks/0j3lsvnh0hrho.js","revision":"889d3f89e4977fac8b1cffa2ba3c347c"},{"url":"static/chunks/0ixq0s2ee7ism.js","revision":"a500dd4a3dcd78609f72c1b09e6397ba"},{"url":"static/chunks/0itwg58r-f6uy.js","revision":"48a24d1233ee515704734a6833084448"},{"url":"static/chunks/0irqueuvs_ap0.js","revision":"d6d032c1bb65621c3a640e893fbadeeb"},{"url":"static/chunks/0icjytvdsjvj2.js","revision":"d9037b97b2ce7dc038c9f2b35714970d"},{"url":"static/chunks/0i0i_-h2u6f4x.js","revision":"1818e7cf56c26f8e9660064fe45119e1"},{"url":"static/chunks/0heupeekrxhf3.js","revision":"93c692b452cc328a28ecd09bf962210d"},{"url":"static/chunks/0h1ugwqjvgd5d.js","revision":"90ec2ee0f2440ca0dad5e2ab65e67d89"},{"url":"static/chunks/0h-t3j9d7t435.js","revision":"8ab188f241b4bd24bb63ea46a1c7d8f7"},{"url":"static/chunks/0gs6bdgjeqclt.js","revision":"5cc6c155eb9918e4e5151601e0902bb5"},{"url":"static/chunks/0g8n9yx3kw1vm.js","revision":"dc590880934f0355eea08906a10ec7c3"},{"url":"static/chunks/0fwbwcshkdu-4.js","revision":"b63c38c61a97c0bf5357990dcbf09a61"},{"url":"static/chunks/0f_gupknmgcj7.js","revision":"d584455e8b1fc312873e134fc09e981b"},{"url":"static/chunks/0eslf3itn-53v.js","revision":"9f07a448ad29a1abd99bd6ae94b06c81"},{"url":"static/chunks/0eqdm8c9-5gj6.js","revision":"061221802a30e09478a4d53577e70bb9"},{"url":"static/chunks/0ele452jt91a1.js","revision":"a93051c318548931aa2963151e760596"},{"url":"static/chunks/0dl6yhptpm4oe.js","revision":"c507fe473d5b32fa82c584d42d0620fc"},{"url":"static/chunks/0dk8vljkl_k7n.js","revision":"60d1690e8b19927a7df643c9c46ee48f"},{"url":"static/chunks/0d6tk29hne5dg.js","revision":"1d3e89681ca2ca870775a8962b19ffb4"},{"url":"static/chunks/0d5oimhojdy-t.js","revision":"4f0718385765ca2a157dfdce64197b4d"},{"url":"static/chunks/0d-gzcaf1y9s7.js","revision":"47f7c306f8744182acc017ffe0e0341d"},{"url":"static/chunks/0cz1d0mv5g_q7.js","revision":"846118c33b2c0e922d7b3a7676f81f6f"},{"url":"static/chunks/0chqe3jr549ko.js","revision":"35dd8dc96e4fdb400f56dea529902f15"},{"url":"static/chunks/0cf2l18wijq1v.js","revision":"d31adbf1c64a3fee5d9ac2f5bbfc809c"},{"url":"static/chunks/0bzramt5c-rzx.js","revision":"22166112f3db016c2f6b9e014a50d8f9"},{"url":"static/chunks/0bgv-a2wg0kqb.js","revision":"de15bb6df6830c21077b85f81aa1242a"},{"url":"static/chunks/0bfyvc5x0t1zk.js","revision":"8ecd9c93f73de541a8cd3a363231fa65"},{"url":"static/chunks/0beh-acmlb6--.js","revision":"61c4a46ad85a7cdd57f6f661c5e4bdc4"},{"url":"static/chunks/0b2rm02pt_4i1.js","revision":"ad512d43b60b550db1e83e655162224b"},{"url":"static/chunks/0ayu6ztmm88bg.js","revision":"d4151f81108caad13227ad7cd08e6723"},{"url":"static/chunks/0aya0w_wd2lu0.js","revision":"2a773546dbc95297bf0504b6a9fdbe0e"},{"url":"static/chunks/0aw2b-xxyq0cw.js","revision":"af8217663f7067d87f0f614d1e67f34b"},{"url":"static/chunks/0au83t7x142g1.js","revision":"c8eaa3a2b9a645d9bf5db9fb55eb7aba"},{"url":"static/chunks/0apneoff_llm2.js","revision":"f4047f22e76f39151f17c171d0feda91"},{"url":"static/chunks/0agzfl02-gufv.js","revision":"9a079e7102fd7b1bfc2eab1fe7c8079e"},{"url":"static/chunks/0_wwkpr-rymsi.js","revision":"72198fd7bb7d92f450d47ee719a5ed57"},{"url":"static/chunks/0_snbvnz_ulpv.js","revision":"505d66ca0941af233b4d9f267127a0ce"},{"url":"static/chunks/0_jki5u8vmuvz.js","revision":"17d9611cc50e60a94bec267370aabcc8"},{"url":"static/chunks/09nggdb49ctn3.js","revision":"8e4b5148b72c5ff5d379583d63b148f4"},{"url":"static/chunks/09a73o9v_nz9i.js","revision":"4aac4b342a8c0fc3cc557e6f219d4ac2"},{"url":"static/chunks/089bufybl4mol.js","revision":"459dae218f98068fc8807beb3468c42e"},{"url":"static/chunks/088m9nvqp8yy3.js","revision":"52a878d33ec3faebc6e6d74df8df5509"},{"url":"static/chunks/0858lh13l17n9.js","revision":"69b1e0fef6c16d960ecc13a020d0bbaa"},{"url":"static/chunks/07ico47tjxra0.js","revision":"c08b16a0405e692685bef8a5304ad31c"},{"url":"static/chunks/07dd7ii1w7njn.js","revision":"c1bf926093185161406519d790f37610"},{"url":"static/chunks/07-spgqxialxl.js","revision":"20a38282ea71bc1738e3c6140d343d02"},{"url":"static/chunks/06zd_6djyii-9.js","revision":"4fa47d0a9994db43d103cc5f8789abd0"},{"url":"static/chunks/06g_6p9ijq0ra.js","revision":"4d25c4de93617b44aaecc78cc9d49bf5"},{"url":"static/chunks/067zyctm6q35o.js","revision":"e7a58c95c213ece23c1c62c6212134d1"},{"url":"static/chunks/065eq7bb6ocz0.js","revision":"942f666a244f5fd5e32d86923309bf04"},{"url":"static/chunks/05qc9z4j2mvwh.js","revision":"e0890d8f1813212d82cf50211018dca4"},{"url":"static/chunks/05hxvobe6-zzm.js","revision":"22eb0b0e587c46a7d5e082e875db5998"},{"url":"static/chunks/05fzngxuocaym.js","revision":"dee82192e25688e3203c79b273fc28fd"},{"url":"static/chunks/04uv-d4y29rq2.js","revision":"b7e6840365e73425923e7bc7262a98ef"},{"url":"static/chunks/04b3yz-e-8gj5.js","revision":"816968ae913fd6dfc80baa476449882d"},{"url":"static/chunks/03oltae8hndf0.js","revision":"29856b30d5bf3538fa016b977977cacd"},{"url":"static/chunks/03imnsy7qso2e.js","revision":"1489268af1a2bad152631f0f0b643f72"},{"url":"static/chunks/03hn4zwtalkzy.js","revision":"a7183a38168577acb5c512ef7f898abe"},{"url":"static/chunks/036wmdcwgd4yo.js","revision":"9f99b21cd3c789b60d117ef16b976e54"},{"url":"static/chunks/0365f-0esipxv.js","revision":"47e1232c9149ac565eee0517b85f8255"},{"url":"static/chunks/02u_k8w9aoxa3.js","revision":"bbcf847192411f7c19c5b9ebe5f6d1f5"},{"url":"static/chunks/02md865ad91qr.js","revision":"bfb13a81c2b31215a6ac49a3d57e4551"},{"url":"static/chunks/02_rtyb7egu4_.js","revision":"aae9d8f99440c1290977ed7d7e18fef9"},{"url":"static/chunks/01kwu8cb_latw.js","revision":"25d28d2c1da8fe4c102c46c49255816b"},{"url":"static/chunks/014g6-_4t1_2h.js","revision":"e4ad73e11725bdf8633f602ae7b99c18"},{"url":"static/chunks/0-z4_yaplhw89.js","revision":"a30fec88c495b5254dd1dc667dc2c199"},{"url":"static/chunks/0-yf0gbo0f8q6.js","revision":"33f0c01b796958783776e2e81042a844"},{"url":"server/app/_global-error.html","revision":"1a19546cdada4bac502b967e3aba4fe1"}],
  skipWaiting: true,
  clientsClaim: true,
  navigationPreload: true,
  runtimeCaching: [
    {
      matcher: ({ url }) => url.pathname.startsWith("/api/v1/chats") || url.pathname.startsWith("/api/v1/agents"),
      handler: new NetworkFirst({
        cacheName: "myrm-agent-api-cache",
        plugins: [
          new ExpirationPlugin({
            maxEntries: 100,
            maxAgeSeconds: 7 * 24 * 60 * 60
          })
        ],
        networkTimeoutSeconds: 5
      })
    },
    ...defaultCache
  ]
});
self.addEventListener("push", (event) => {
  if (!event.data) {
    return;
  }
  let payload = {};
  try {
    payload = event.data.json();
  } catch {
    payload = { title: "Myrm AI", body: event.data.text() };
  }
  const origin = self.location.origin;
  const safeUrl = sanitizePushTargetUrl(payload.url || "/", origin);
  const chatId = chatIdFromPushPath(new URL(safeUrl, origin).pathname);
  const title = payload.title || "Myrm AI";
  const options = {
    body: payload.body || "",
    icon: "/favicon-32.png",
    badge: "/favicon-32.png",
    data: { url: safeUrl },
    tag: chatId ? `myrm-${chatId}` : `myrm-${Date.now()}`
  };
  event.waitUntil(self.registration.showNotification(title, options));
});
self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const origin = self.location.origin;
  const rawTargetUrl = event.notification.data?.url || "/";
  const targetUrl = sanitizePushTargetUrl(rawTargetUrl, origin);
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((clientList) => {
      for (const client of clientList) {
        const action = resolvePushClientFocusAction(client.url, targetUrl, origin);
        if (action === "focus" && "focus" in client) {
          return client.focus();
        }
        if (action === "navigate" && "navigate" in client) {
          return client.navigate(targetUrl);
        }
      }
      return self.clients.openWindow(targetUrl);
    })
  );
});
