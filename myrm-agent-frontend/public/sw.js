// node_modules/serwist/dist/chunks/waitUntil-BHDx3Rgo.js
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

// node_modules/serwist/dist/chunks/printInstallDetails-c9A08ZVZ.js
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
  precacheEntries: [{"url":"static/chunks/turbopack-2l99udl08uj-a.js","revision":"44292b9c70592ce464f01a4e77150db8"},{"url":"static/chunks/458idnvacug66.js","revision":"51e8e3d6959554010aa6a20f06504dba"},{"url":"static/chunks/44v0hwlovk81a.js","revision":"5ea5addc07c510ff9767e8b1298de469"},{"url":"static/chunks/448t4vi3gos5-.js","revision":"bf53108b073d5d7bcceb61327296ca09"},{"url":"static/chunks/43m0d06x_1oqj.js","revision":"b64223dae7c915b68248270d2bf72a59"},{"url":"static/chunks/43h07yrsfrd7r.js","revision":"ac79fd719f1b1b78b07efc11c3bc6735"},{"url":"static/chunks/42m9awy8tme6x.js","revision":"fec72cc2db41fe1f6dd804f79164cb72"},{"url":"static/chunks/41kify4j38uyk.js","revision":"9aeddc99b559b04a87bd9d8fe8ece3fd"},{"url":"static/chunks/40v8lhm0tl3qn.js","revision":"012f07742da668e46282555d7f07f84c"},{"url":"static/chunks/40sectrh0ea4h.js","revision":"d6754b1fa2150259f9a1c0ef2554a3c3"},{"url":"static/chunks/40a25bcnzte7a.js","revision":"5afa522b0d11385f825dd744f90de243"},{"url":"static/chunks/3zw7of0ot5-y6.js","revision":"04551b704391e9f15d866597874514f5"},{"url":"static/chunks/3zl8llo9t10-5.js","revision":"e22e4a9cb62a509f524bc49e15c1a228"},{"url":"static/chunks/3yk9ax8bo3jbz.js","revision":"5c1d199f9ccc855e19ede05277d036e4"},{"url":"static/chunks/3yfh0d_ht69j3.js","revision":"27ce3ac564d48a72285124bb76ac9f9b"},{"url":"static/chunks/3y4oi6uck4g72.js","revision":"70931855d6c42517df1c353b15a2bc8a"},{"url":"static/chunks/3xpff_tfiwtwa.js","revision":"28fbdf374f74c48d3f1bf871f7a511e6"},{"url":"static/chunks/3xoiwk42va0kj.js","revision":"70c7fbaf6419edbc6ee48b5b1dbb9b65"},{"url":"static/chunks/3ww7bl1nh9mv2.js","revision":"115299b5fc1a39a4a96f1eeb3dd440b4"},{"url":"static/chunks/3ws6asqmdhnr4.js","revision":"9d09e44a2f88ff522413109b336a9fc9"},{"url":"static/chunks/3whutf3xa3hcn.js","revision":"9742e86007b633cb4b2cb1d4669dd06e"},{"url":"static/chunks/3wbjrf6i0b_sr.js","revision":"a2d5badc77212cc984c3035af1d9e259"},{"url":"static/chunks/3w8d0p40wh5cs.js","revision":"bdd4acce4f7ad3950a526e715e040ea0"},{"url":"static/chunks/3w-s04jff22od.js","revision":"861771b17f1782fcf698eb8c57c501c2"},{"url":"static/chunks/3v7nhjxralh2u.js","revision":"5d1c25592e2269c432ba216245e25380"},{"url":"static/chunks/3unzf0btkxlfv.js","revision":"2c99a1d0feff4cd54e109e95fb77ed01"},{"url":"static/chunks/3tqw1-_4b1idb.js","revision":"b7ea2aa2aa4e449ff32bfb4f273ff7ce"},{"url":"static/chunks/3tm0xfmw_e_pq.js","revision":"eb55b07a89ea72ba11fd947d6847315c"},{"url":"static/chunks/3tc1jdi_xhvl4.js","revision":"6e6675f9a487d4171cbe59aeaa440525"},{"url":"static/chunks/3t1vrllvwpn9l.js","revision":"9481cc72fc9b661e554573c03ac66952"},{"url":"static/chunks/3t-u_m7mkcdfu.js","revision":"2c807b72ddacd1f69f99f808019ae84a"},{"url":"static/chunks/3snns03b2uuj2.js","revision":"2705cc5e7de78362347fa607389e770c"},{"url":"static/chunks/3si5ilsydpg9k.js","revision":"cdb45aa6dcbeb6f1b59e4b0d117325b0"},{"url":"static/chunks/3s5zy3of-elt0.js","revision":"3cbce16ff7d4555226ea0baaf3e0898e"},{"url":"static/chunks/3riezlotc3eih.js","revision":"a0dff3a205bd570a3ee16cc5b4f23093"},{"url":"static/chunks/3rek8qpgn3czm.js","revision":"b08846f511b3d12dec5efcaaf754ef6d"},{"url":"static/chunks/3r7yklb7uyk_q.js","revision":"5bf1938b9e213fcc54bcc964d7e7f912"},{"url":"static/chunks/3r55420d4lg81.js","revision":"5d1c343a7e44c1cb13e4d48dea9a46d8"},{"url":"static/chunks/3qisidn9b59pt.js","revision":"c6d3ba02df272b68b55af28230da29cc"},{"url":"static/chunks/3pshjw05jsrri.js","revision":"64cb71bf033794a2df279e9b54093fba"},{"url":"static/chunks/3ojb3vjljodwa.js","revision":"acea8f2bd7e236d8c802063e7abe9171"},{"url":"static/chunks/3nu9olhtt0h7f.js","revision":"c4c1e92eebeba3a7907dd5b4b3bc5eb8"},{"url":"static/chunks/3n0o9bfqid4ty.js","revision":"44e3320b70f0173877e0f37afedb86f9"},{"url":"static/chunks/3lukwiugfyhxt.js","revision":"fee2a18cb6ec7f857eec48d2bf145313"},{"url":"static/chunks/3lrjyk0a49vvh.js","revision":"77870569f3fd5b33f304b82e3bc043dc"},{"url":"static/chunks/3llfryuelhh8q.js","revision":"95877d66449a8062262b522bcba47b36"},{"url":"static/chunks/3ljz5qioajiui.js","revision":"ec65ebef7f837c125dcaf9a085016384"},{"url":"static/chunks/3ldgyaat0tt3f.js","revision":"dfb1edbe0e5dbde457d142433f90e871"},{"url":"static/chunks/3kp9derkabmk_.js","revision":"6743c672a9fff526b449124101fa01e0"},{"url":"static/chunks/3jve3q_sd2f1m.js","revision":"cb61f19970a15de45116821d7ad25e75"},{"url":"static/chunks/3jrcpfo7vhxju.js","revision":"dbbe8cef52eb3988a47387e617b6ea40"},{"url":"static/chunks/3jbaxjsfuk7y_.js","revision":"0ecdf470b09e96ecd60e76828c1c8eaa"},{"url":"static/chunks/3iy53i8m9i1p7.js","revision":"d5c18c8b1341c0168b721f8c20c443f2"},{"url":"static/chunks/3ihxi7mrwzfs1.js","revision":"c70aff7dbec5eea54dbbf4faf73d8d95"},{"url":"static/chunks/3idcbthapeix7.js","revision":"c1a969aaaeb7236ec0cfdf5388c14248"},{"url":"static/chunks/3i8nh3-nqd24i.js","revision":"ecf5d36486714d48f232f1de15285f54"},{"url":"static/chunks/3i6lg6c34xpoj.js","revision":"c7385544cf049b740665f8b83d7e2a1a"},{"url":"static/chunks/3i5gn7n_w8a3n.js","revision":"ae34c65d7262930ef11ffe7edadb578b"},{"url":"static/chunks/3i318k538lepj.js","revision":"303cab9d3c2c667fd89146a02ab3080f"},{"url":"static/chunks/3hw2u-tcjd4-c.js","revision":"1eb02e8b9f1ad99f25cbe24f47e6e879"},{"url":"static/chunks/3hknsjyz-ewik.js","revision":"36d4bd990fe289f685f8968dfd1fc7ee"},{"url":"static/chunks/3hhb_jrkpdsbh.js","revision":"ad41c0cbd8036f587b9d1afb7f67da36"},{"url":"static/chunks/3h_dxsbhnoros.js","revision":"beaf038d2abd3a8c55fb26ae8ca5ae78"},{"url":"static/chunks/3ggwcn_zw-z4_.js","revision":"9a79d6c40504895c6610c08c224ac828"},{"url":"static/chunks/3fmhw178pza6s.js","revision":"b11ad775343f305d4304bad7fd5996c9"},{"url":"static/chunks/3fd9a1o-va22j.js","revision":"0d028fceb0df136f55053a5e9a3c4b1d"},{"url":"static/chunks/3fa1s_e8a3_96.js","revision":"533bbe5e2388ed8ecd7754aa43f07605"},{"url":"static/chunks/3eyhl2ub_j0ce.js","revision":"d307b987aa57697e1631f5ac976838ff"},{"url":"static/chunks/3ew6z4k24vzdi.js","revision":"84c3a0ca64a9bf1d098853b37bdb2fdc"},{"url":"static/chunks/3egaa_amx0x9m.js","revision":"eb977e46c8133a51d6a682b278aef9b0"},{"url":"static/chunks/3e_ut9yinvw_h.js","revision":"0357de425708dc0ca279eec2f28d075a"},{"url":"static/chunks/3dp1pa_8ug_6b.js","revision":"d525d1d885404c94803d68fc991aba71"},{"url":"static/chunks/3d6u8axdhk28u.js","revision":"a5a7804c3f5632e5569d7335546fd17f"},{"url":"static/chunks/3cyas1qpx0ixv.js","revision":"b06a42ff6c581aa5ce2138cc6ef53478"},{"url":"static/chunks/3cfsts5jr9jj8.js","revision":"d6d3abc71b695eb1e36143e6b3b64940"},{"url":"static/chunks/3cb6zvgqrbec_.js","revision":"501441d53379d49aa527304e49d482c7"},{"url":"static/chunks/3btikhzq7yrgi.js","revision":"e4238f7e16ee451870c37fcf0e6c8a01"},{"url":"static/chunks/3b7m5yht0t0o5.js","revision":"db71601e761bd303d15802393d85c52c"},{"url":"static/chunks/3b4px5ei139a4.js","revision":"d6b16a510db5d8febb40dd4fbea2c640"},{"url":"static/chunks/3auwghz132a0s.js","revision":"729f0f63b923e233516585083fe4eac5"},{"url":"static/chunks/3a1ul_mj3zrol.js","revision":"5b78c9e4031488e81f5001210cb6967b"},{"url":"static/chunks/3_sfca1xfd051.js","revision":"c33430ec701abf5c8f95e59bee6d8190"},{"url":"static/chunks/3_rpyjfa0s2bd.js","revision":"9f26a2e1ce745f416ece5730d7265c0d"},{"url":"static/chunks/3_reaj6xv1grw.js","revision":"41242b4312d74b0d2ed381931bfe4468"},{"url":"static/chunks/3_n3mbayio8fg.js","revision":"a37553a052aa7b1a065d21248122a569"},{"url":"static/chunks/3_db_qg1_-bos.js","revision":"7151ee8069ebc1acb112cfafd68b775d"},{"url":"static/chunks/3_ayhck8m8efu.js","revision":"c90c872ed4a3ad31532863cfcd1f72e0"},{"url":"static/chunks/39z937-xoli3u.js","revision":"81a4f317403905e67cbeb44b8277cf0e"},{"url":"static/chunks/398au-dydmlg0.js","revision":"07f9084132f306bdcc9fb8ce04a80e61"},{"url":"static/chunks/38ru5p-4vwqr1.js","revision":"a1069b47963a9132dd38cb029c576774"},{"url":"static/chunks/38-6qxv9g3-54.js","revision":"913d9a5c41b18be6630b3813bf1f756d"},{"url":"static/chunks/37y02jhc0deci.js","revision":"8cb32823c927c4635115d2a0a6f90d49"},{"url":"static/chunks/37wql7x9mbbtw.js","revision":"3f282e5a759257511e41ae341e5dba31"},{"url":"static/chunks/37sbahn3ms4-g.js","revision":"7d835a6c3bb4d14ec92ff24a3d3eec21"},{"url":"static/chunks/37pb95-aeq2mw.js","revision":"0ed2f9b69944f7cc8c26b597b5a2faa9"},{"url":"static/chunks/37a-35qrt9kxw.js","revision":"0c66815b18190a777c5282a7f22a1ecd"},{"url":"static/chunks/36ztsw_jyg23n.js","revision":"92cb0cb428885a0f6923a5c001dfc0f8"},{"url":"static/chunks/36ztrh9y96swp.js","revision":"32c308ac6acd14f62d4d707597fc8f00"},{"url":"static/chunks/36r1udzfotwwj.js","revision":"3d3b768ce47d5c2640d9c633f8382c39"},{"url":"static/chunks/36d8xqgh3tpx9.js","revision":"ed4961b6c7cc38f08bf8cd5e3411fb7c"},{"url":"static/chunks/367wipz0afqf3.js","revision":"bc4b9681bfa27f483d48406930fd2086"},{"url":"static/chunks/35zyivyh_q42t.js","revision":"2baa0b693916deb5bd7b25acdad76da2"},{"url":"static/chunks/34mmugjqdxv7y.js","revision":"542d305cfba6bbf5161e10f4d2c1e031"},{"url":"static/chunks/34f731zis89ob.js","revision":"b8bc0a81ba5b7783880490f229d7f85b"},{"url":"static/chunks/34-sjciv4bcyl.js","revision":"ea09dcf1e502348d0bd59f0c167c6810"},{"url":"static/chunks/33vajikn5g1cr.js","revision":"5c180f61c4edf8578c6bc6189dddf514"},{"url":"static/chunks/33u67sj2je-jf.js","revision":"6a5716420b5bd8c2fc1c8fc70da7987f"},{"url":"static/chunks/33pztzz16zjr0.js","revision":"903c69714cd3428ba7bfebc24b84594e"},{"url":"static/chunks/33ph0q2nr23m2.js","revision":"965764b09e590313187892d9d5810a0a"},{"url":"static/chunks/33f2yw24ozdhr.js","revision":"68f35b38a56a760b3c0eae71496a88cd"},{"url":"static/chunks/335m2v4jlmsan.js","revision":"88e7b3656d102bd22c2ae64ee13d590b"},{"url":"static/chunks/32cl6qwgz3rjh.js","revision":"c4258374a5fadf6caa84ddd7534931c1"},{"url":"static/chunks/328m8rudr12c8.js","revision":"95be9bec482e1023ffb8ba1ec6e41c30"},{"url":"static/chunks/322_6lfa8efcp.js","revision":"7db0265b302348309478f5d8286285f6"},{"url":"static/chunks/31oam42pi5522.js","revision":"682b566c17ccbd12b45da9bc129bed6a"},{"url":"static/chunks/31n0nlf5mclri.js","revision":"381951f86b7f45e7fa31988bd1864564"},{"url":"static/chunks/31a169_a43vd-.js","revision":"c8be0fe427ac0d5b4f5cfd53cbc4f194"},{"url":"static/chunks/306wp2i4mndk-.js","revision":"eb13546107cb9a7acd9ed88abc018db1"},{"url":"static/chunks/3-n7_og8e5ra2.js","revision":"f97059df787e325b8c0bdbc427205d13"},{"url":"static/chunks/3-fwa38vkdbr7.js","revision":"b151fa05b8c4044ce1f2e5743b59e8c3"},{"url":"static/chunks/3-4pwasgb2qdk.js","revision":"bc1a7bf1489a68acdc57fcdc2f99189e"},{"url":"static/chunks/3-4ppylfneqp2.js","revision":"7960034bc0a11e3624052879b69f2d04"},{"url":"static/chunks/2zzfc1xekckni.js","revision":"7b8365942cb6719592e7bfc7e19b95a4"},{"url":"static/chunks/2zt6p6x55jqcl.js","revision":"bd4f8f275fdf48110c1749980ec31c15"},{"url":"static/chunks/2z1kctdczzbtr.js","revision":"e61912b267294d058084687a96d36a70"},{"url":"static/chunks/2yjafjr9l17g_.js","revision":"f448a60f85386637ef6eeaa5e1fca613"},{"url":"static/chunks/2y-w_cvbk-ed-.js","revision":"97333d4aad36e137dc4da11f9e933ec7"},{"url":"static/chunks/2xrvw1g97jh51.js","revision":"163a486e5b6630c1864ec507e528e3ed"},{"url":"static/chunks/2xat9-2gwv139.js","revision":"9726bc3d2ef2f331f2f19f6ab06792e4"},{"url":"static/chunks/2xa8qo7lfx7uz.js","revision":"35181bc84ec5deea5a094924c0840d12"},{"url":"static/chunks/2x9d9oe18ot5z.js","revision":"f4adf4e9367823ccbeb6497f0e01c752"},{"url":"static/chunks/2x1896oasv0-0.js","revision":"1c17fa8947eb3621cba2e64b96290f79"},{"url":"static/chunks/2wp6jgb_bnlww.js","revision":"944fc12fc340e33e09ed580b91f8d00d"},{"url":"static/chunks/2wf7tlmald2r_.js","revision":"7d9a4151f3eec5a03438dd5414a01c30"},{"url":"static/chunks/2vt0jhu28kvre.js","revision":"85e230fb4bb4b36aca48e2600c4785e1"},{"url":"static/chunks/2v9g2levhgdfi.js","revision":"b732c3452bc30ff31916dcb38368de32"},{"url":"static/chunks/2v6_86pm4-7yr.js","revision":"a2c1115038c6db44018baad9010f4516"},{"url":"static/chunks/2uv5aw7mt7ix-.js","revision":"a0b842ce41deb55630c943fd745b7c1a"},{"url":"static/chunks/2uqwpdc92t2h6.js","revision":"4fd2abdc2fe43df9cab8490f2d9591a7"},{"url":"static/chunks/2ui06u3ft4uys.js","revision":"2c9ce12e2da2e946ab9f09d98ba3bcef"},{"url":"static/chunks/2u82ktxcd1_fv.js","revision":"b06cfe9a2a605f3104b0205768c97f07"},{"url":"static/chunks/2u1jvtaa2vf55.js","revision":"b4b216ee9af995189a2f8740355eb617"},{"url":"static/chunks/2u0w0e_05bcyc.js","revision":"98518c58a65c8111d4a1e21437d52c55"},{"url":"static/chunks/2tyx8646n128z.js","revision":"3a6cf26811686e8fea4d79b4e993430f"},{"url":"static/chunks/2tmv3pteiti4c.js","revision":"5b3338d098c650f7cac6d434f0991032"},{"url":"static/chunks/2tmhs81t4o2o4.js","revision":"9f9767bcac34dfe5a9dc7cf62b91fa18"},{"url":"static/chunks/2td7g6f36ar59.js","revision":"d1bffb8986bd04ea7e6f552ca6c44a40"},{"url":"static/chunks/2tasfotai_99y.js","revision":"08bf6535e75de0e4fbfcfb800c7a1998"},{"url":"static/chunks/2t_z2yri8bzns.js","revision":"0f62d76caa67a2cc3f7bf4ebc32c173e"},{"url":"static/chunks/2t62p70t40b71.js","revision":"047ae9e630138597b35d921fe1f12dcd"},{"url":"static/chunks/2spf3hwkknif_.js","revision":"a35c099df1f214bc759e630db5423ca3"},{"url":"static/chunks/2rb1x39pgsmyv.js","revision":"6b58db31c23a4721d454e27d164f56c4"},{"url":"static/chunks/2r_14nec39wo0.js","revision":"a101f1a9efcdd2115b26967993ad0f57"},{"url":"static/chunks/2q3wnphoz0zoq.js","revision":"ded46c5c126790ca3f24dd8e658c3fb9"},{"url":"static/chunks/2px_r2sxr-5mn.js","revision":"04cb3afe7d6cfeb8ee128259593fc6f6"},{"url":"static/chunks/2p-mmbc82rtfw.js","revision":"b77efac13de0661c665d6ffc0644a930"},{"url":"static/chunks/2ob_06frzr00c.js","revision":"71dee642ff0caf66987c5289fade9efb"},{"url":"static/chunks/2o19569y5-np6.js","revision":"3c078169d93887fbb60fe364bfc6eb69"},{"url":"static/chunks/2nyavinh8-9_2.js","revision":"474ec8c7e92cd1f09ea9b5056b1a4592"},{"url":"static/chunks/2nmmmtu3q374k.js","revision":"f5375ab9c8d51a047920d0e7fa00d940"},{"url":"static/chunks/2nfnz70k0u4sp.js","revision":"795136c38ee81547b948ee8974cf5f0f"},{"url":"static/chunks/2netrwn_4p7w8.js","revision":"d725fc8bfb1602af6fcd61e7aa8c5df8"},{"url":"static/chunks/2nco-leefbm4z.js","revision":"39fd1bad4908070a071f38b498ef6c6e"},{"url":"static/chunks/2n7c5tirb1ebp.js","revision":"57c8ca00612bd473c1fd8930b265b3d0"},{"url":"static/chunks/2n-yj2wj0d4vi.js","revision":"3ee33fa752a24bedf7a8856caa422c70"},{"url":"static/chunks/2mt76m-kszien.js","revision":"aded539fd1c7790db4893980798a52b2"},{"url":"static/chunks/2mr0j0e9s7q1y.js","revision":"7e165e1c71304147c90b0eb6daa4f0a9"},{"url":"static/chunks/2m5mn8rahzm0v.js","revision":"063578419a62f965b8ea545080f2e4d1"},{"url":"static/chunks/2lqyp6sjcse5n.js","revision":"f4b96ea93bb77410576d28b7c30bc198"},{"url":"static/chunks/2ljhcm8ct66w9.js","revision":"9a52bbd4d0b731be2d818af393cb9f89"},{"url":"static/chunks/2l13hljp72n_b.js","revision":"cd081e5f4c8ee1c1fa0f9600a5c225df"},{"url":"static/chunks/2kx_6j8--aptz.js","revision":"b1da7cbfa1d6348d6e4e6d41e70c948d"},{"url":"static/chunks/2jxrv_7h3nt85.js","revision":"2ff051fbb3acd49f3112caf7d00f2c53"},{"url":"static/chunks/2ijb3wg_vthmk.js","revision":"a487ff3b94a791133479ec4d874fd95b"},{"url":"static/chunks/2ie-mugn2wtgu.js","revision":"aa455c52983b8fe78be01a3f317aa8ca"},{"url":"static/chunks/2ice73alaz1mx.js","revision":"480b40bfe9c5066f444e6c0d0c3976f5"},{"url":"static/chunks/2i_b70tzm_bvv.js","revision":"55056e309e2b84710ad9447597829c9a"},{"url":"static/chunks/2i802z8pyw-2s.js","revision":"814f72c92bf51a833b4cacda29b3dd9b"},{"url":"static/chunks/2i7yrsyhjixal.js","revision":"1537196501c5439f669b58d0679f273c"},{"url":"static/chunks/2gsqiojrhlr6s.js","revision":"ef89bdaef78f17351b548ffeca2227b2"},{"url":"static/chunks/2gnp4vrss8z5y.js","revision":"4c44218792b5c5bc844274064d286103"},{"url":"static/chunks/2fxqkujnn2ffz.js","revision":"5be995bd97627596f0b2215488188537"},{"url":"static/chunks/2fsy-in7u2lor.js","revision":"0bb925b1819a994c92abf86a2a2b735f"},{"url":"static/chunks/2fb4rrhop1e8j.js","revision":"b3e5a4454071a72838c5f74da1273842"},{"url":"static/chunks/2f6-nj2ltc913.js","revision":"dea0d672dd99cfcbc0de9bb4981ac834"},{"url":"static/chunks/2dagl2a799wor.js","revision":"b0754b71ee7ed4c23a41371587985e03"},{"url":"static/chunks/2d8hs9z4rtcbn.js","revision":"086ec65d34b3a424d47ab459b3a7781a"},{"url":"static/chunks/2d0b8qcq7hem_.js","revision":"18f08a685e26beea29e016d8b983ae23"},{"url":"static/chunks/2cxnsfxk-97rp.js","revision":"98a0c2a26389104467c3b72a8e24bfa0"},{"url":"static/chunks/2cswq_183m3j_.js","revision":"b11bb5a12284b69143d7f0c2053ed5ee"},{"url":"static/chunks/2criljn0gwpej.js","revision":"0d0915c1e8e3eadf816a0ccb1de3423a"},{"url":"static/chunks/2cd19fszf9nmj.js","revision":"7b79348292d2bbaecfa3c4240646ca02"},{"url":"static/chunks/2bg66kpvq-5an.js","revision":"9f3cfbe05c8355e21abb63ad53bb2b0d"},{"url":"static/chunks/2bcl3n-6efh-0.js","revision":"2cef1aa424b0ba7fedb982c639ee2e7a"},{"url":"static/chunks/2b-e81g9zl46-.js","revision":"c14f16e71977053ea4144921bc10709f"},{"url":"static/chunks/2an84yekdjkgg.js","revision":"cbb5273779091fe603ffbcd4bc904c65"},{"url":"static/chunks/2af_u9ntz-_yl.js","revision":"8eadcfaaf74f8ec444141d8310f7475c"},{"url":"static/chunks/2a2nt1mk-c155.js","revision":"d0a4ce7d69fc631883380f7fc708264f"},{"url":"static/chunks/2_orjdpj2awc5.js","revision":"597ad63c874d6efd80ff96ac4180133c"},{"url":"static/chunks/29pjsn3-5m0hc.js","revision":"10b32a328fc68aaf363e7968efd074d8"},{"url":"static/chunks/29ju69hg43anb.js","revision":"01dc0f63a58278d4056ae33908b5004c"},{"url":"static/chunks/291c8zvy2bljj.js","revision":"ed43362a6e9573f8cddad68cf9253278"},{"url":"static/chunks/28tpiqf-j5tkb.js","revision":"100ee710c1b2c67221d14ba2da3a1ca4"},{"url":"static/chunks/28sl7vle9ngjw.js","revision":"f12d91b96569fc5c4634b95479b722ea"},{"url":"static/chunks/28mi352g2zs_z.js","revision":"6ee7d6a3d3c9654e81b679b27cca8809"},{"url":"static/chunks/28lm4i1se5rek.js","revision":"62b469d77c0205060986de6fb2703106"},{"url":"static/chunks/27jnekq7spqjp.js","revision":"a6980d7f4fd74464bf679f0160024383"},{"url":"static/chunks/27gmdgmfbrdr7.js","revision":"5c67cbd1f8f0c243bcf072a63c55ff95"},{"url":"static/chunks/27flymvk3vt2f.js","revision":"421bed5eee19c055217c25f142a9ba63"},{"url":"static/chunks/26jsfh82clw2e.js","revision":"101c511086e17baa7889f5f639d99a3a"},{"url":"static/chunks/25fv0vfh1yvt4.js","revision":"179677435f6620546fb367253b2c062d"},{"url":"static/chunks/25fowfa8i3y5g.js","revision":"4276023825350574a44d2a618c2aec40"},{"url":"static/chunks/25-wx_h-b44c7.js","revision":"68c58da4929dc83636e4abe129420467"},{"url":"static/chunks/24x251e-wpxn6.js","revision":"38d34e220b9cb5cc31a69eef4c870f86"},{"url":"static/chunks/23xly7wom6_yn.js","revision":"5724febca4614c562f92e04d61ce9793"},{"url":"static/chunks/23npu6qo3c-zh.js","revision":"c825eb1a35896664edc9f0105caace78"},{"url":"static/chunks/23i1iidn8qmr9.js","revision":"0d0c25c58f3fc74bb347c4d2c0852903"},{"url":"static/chunks/23fcmfe6zmz40.js","revision":"75b900d79126176e8936e5ea555dfea1"},{"url":"static/chunks/238778hugukw4.js","revision":"63d393a1b7e2307eb901144a08defbde"},{"url":"static/chunks/23-pimd8_r_3k.js","revision":"d745dd83d3a3de18c61ec1635fab34e1"},{"url":"static/chunks/22t4du71a1-kn.js","revision":"cf652c21a1da6ac30cd6af931175eed9"},{"url":"static/chunks/22iv_n8khuscm.js","revision":"bdcc1e33a3cd9c888347ebc48221312b"},{"url":"static/chunks/22dwb22ftazlg.js","revision":"38fa30c46ca2d938e44c7ce25c426e9e"},{"url":"static/chunks/226xsywfv21id.js","revision":"a15bd25f082da7a81a9ad7d66eb8711d"},{"url":"static/chunks/21tgmu_v_y6m8.js","revision":"fbe49f1eace781bee033b312fa62d7fd"},{"url":"static/chunks/21awg7_evrsso.js","revision":"85840afb681f5ce9c6aad5cdabbdf618"},{"url":"static/chunks/20td6x78m8qzo.js","revision":"a696ea824b42b23860137a4658929ad8"},{"url":"static/chunks/203ytfs94_fda.js","revision":"92b7a17b29155dbd4a54685d5c550f2d"},{"url":"static/chunks/2-plc2uyjaz-l.js","revision":"abf9cb053e849a811121641e92edb9c5"},{"url":"static/chunks/2-c6czx7tnelh.js","revision":"c00e1e50d143da166d689ea178db188c"},{"url":"static/chunks/1zr4nrz93be5m.js","revision":"bbb3ce86011436da99aec29f7d960ffd"},{"url":"static/chunks/1zpqq1lg0it42.js","revision":"b5d20b5dfc734ec7c2e397f6174ba4aa"},{"url":"static/chunks/1zhli5ct4nuo3.js","revision":"62db1f779cf6110da31558bcb3021ee6"},{"url":"static/chunks/1y7ps-l2w688d.js","revision":"1c97c22ee9acedee7e44a90ea5bfd6fd"},{"url":"static/chunks/1y2ch8a3ek7ik.js","revision":"d7e1a97382e0db3a1dbedbeaff256370"},{"url":"static/chunks/1y0vp-7h9f38q.js","revision":"14a38b7bb3e7340ab4edd141190c8a15"},{"url":"static/chunks/1xumay126j4nr.js","revision":"4c9a9b560c3fc354cd23fd19c41cd7fc"},{"url":"static/chunks/1xnyrz2grumqg.js","revision":"57cb9e0727e6ab990b8cbd6b3426a3d1"},{"url":"static/chunks/1xi741diggtcf.js","revision":"e41ae92adabc291e83e39f5dda9b746d"},{"url":"static/chunks/1xbsin4ece8zf.js","revision":"fd40eef3b728383b81f05547ff54819f"},{"url":"static/chunks/1xav5pi_e3b0e.js","revision":"283266fec6b1d46acc5607f9de6719db"},{"url":"static/chunks/1x79i2zvzp_tk.js","revision":"c41c842f530e8e3ab99424bccc9f000c"},{"url":"static/chunks/1w0yr77y5r44i.js","revision":"e1d4af31931d2133cce04f63cfd6e781"},{"url":"static/chunks/1vdqqtf1xfhl6.js","revision":"0855c8b886a3697d461f218e47e64471"},{"url":"static/chunks/1uo8djxxo_4nu.js","revision":"1b3e72fd33e70c81c1742c031936b224"},{"url":"static/chunks/1ulmeo04wrqlx.js","revision":"d3ef2e3d07befa2d68b49a160faebd4d"},{"url":"static/chunks/1u_bqam4csiu-.js","revision":"ee2ce3aad6d9f045b6ac6f9a427687dd"},{"url":"static/chunks/1tf77ownh9dah.js","revision":"9a87fa48a0ca80d74447dddd7bd9336b"},{"url":"static/chunks/1t-0juyqz429g.js","revision":"784b4dba5c0c4ce80b67f1aac589b848"},{"url":"static/chunks/1sq73lyevjd94.js","revision":"302d3bc797a98cd9daf2d615ca1fb15f"},{"url":"static/chunks/1s335pm5wl917.js","revision":"bc7a27533cc84674685197b9b6ee6977"},{"url":"static/chunks/1ryapuhdm_zcz.js","revision":"ffee0a846d5cbb6782f7aa0435184e68"},{"url":"static/chunks/1rv3j38dfdc_4.js","revision":"12e8ced3926125e23c1bf58b4f562cec"},{"url":"static/chunks/1rbz-16nh9w_i.js","revision":"1f84c32fc1ef228e8529a83672da6f09"},{"url":"static/chunks/1rbtc363oy_9l.js","revision":"08ad68c280f4ef9cc24d4d12267035d0"},{"url":"static/chunks/1qsgbfkw0xy21.js","revision":"b000915a2289df170bb948743b08e721"},{"url":"static/chunks/1ovxe5vo-dyf7.js","revision":"bcc54d3d2d76248675142bb887dd551f"},{"url":"static/chunks/1oelezqw6ci95.js","revision":"8ca18c5f366a26c89b499b78a5c6a71c"},{"url":"static/chunks/1ob6xzezv33r8.js","revision":"c9ed9564ec036c113ca6fa01e5dee3c5"},{"url":"static/chunks/1oaxf86yvs0am.js","revision":"b15675f93369ebb896a75287ebe19165"},{"url":"static/chunks/1o97zjg4arrf9.js","revision":"36333e0b3db666998c70fbd78e6fb545"},{"url":"static/chunks/1o12y_vxihv7-.js","revision":"a21ce5d6234d4810e1a9802445423486"},{"url":"static/chunks/1nrf2tp5vrryy.js","revision":"f6c6369b94de5331f3e698d9568031bd"},{"url":"static/chunks/1nrd704lafae4.js","revision":"9a790c044cb911f7c9e871fe212f4efa"},{"url":"static/chunks/1nkkpkc3pijfe.js","revision":"995ed2e9988edfa33bd6c0ca49e8f2b7"},{"url":"static/chunks/1ndut5s5q9uu6.js","revision":"aff7d03b4bfe8f936a2d06c05b5b3463"},{"url":"static/chunks/1n6k9v_z3e-8b.js","revision":"11b85933299ad4c1ff0b09c8301c13d9"},{"url":"static/chunks/1mvx3_1gmlr3a.js","revision":"b1f7ead6f5202182ce9f99e8b4560a3a"},{"url":"static/chunks/1m-7lscgrnapc.js","revision":"b7e65513367155fcbdf85ab4b9d3f8a4"},{"url":"static/chunks/1ls_08eln4hmh.js","revision":"ebafb7814f0086ad2a10f245afd88bce"},{"url":"static/chunks/1kmer8d8lbk77.js","revision":"eaf8e06f070f927c91dfca0e8752d8d3"},{"url":"static/chunks/1kbjpnw5vze-7.js","revision":"032dddd4156daa201f116e72090ed543"},{"url":"static/chunks/1jnc_l3shvax_.js","revision":"7d97e2c4c2fdd322afd37d7fc7b445d4"},{"url":"static/chunks/1jb-gtj-_iqhz.js","revision":"387b593d265ca6212ebfe75707774abc"},{"url":"static/chunks/1j3h0q4vqtrcq.js","revision":"b3a4800bcd4376825b2eb3def3c16a47"},{"url":"static/chunks/1igsc2tz59f_1.js","revision":"de5f9a4618c4a019bd91f05ab60d081e"},{"url":"static/chunks/1i6b5na88czjg.js","revision":"80def3a055f9c6666a9a70d07f4df459"},{"url":"static/chunks/1ha3z69q-c-_s.js","revision":"b4754c800f0fdc8e24e0620afe43c50a"},{"url":"static/chunks/1gupsfrbtbfgg.js","revision":"65c778ac14cb94a488280ea323ee98c9"},{"url":"static/chunks/1ey3o912wq99b.js","revision":"018b723937902cb902d76658ef023c03"},{"url":"static/chunks/1euhhe6asjp-0.js","revision":"abb9850c448a00feafb250772e51f1db"},{"url":"static/chunks/1etybc8uk1vbb.js","revision":"c6d0073eb59ac872ed3bb07f849d0c81"},{"url":"static/chunks/1ejpuf-oqco0e.js","revision":"f58939cb515b9bf343c355d56c45e325"},{"url":"static/chunks/1cxecp3pjwk9r.js","revision":"fb63dc3d43159256f922d2a82323bb4e"},{"url":"static/chunks/1cr1-f4hu3vu3.js","revision":"0237c8bf4b12f18cdb683fcdd4d375cc"},{"url":"static/chunks/1c2an21nehfb9.js","revision":"5a05800ed8bcd1cdbb8dff454cc38744"},{"url":"static/chunks/1bosjc1zop-_a.js","revision":"671834b51cc5811c8bccc9e38ed84613"},{"url":"static/chunks/1bg30mn4mb8hb.js","revision":"6480f890a844dc5a7c68b9fd61aac6cb"},{"url":"static/chunks/1awka8pnuq7uj.js","revision":"d48d94cb23081eb7012f96614a367c5c"},{"url":"static/chunks/1abyfc9kvkm7q.js","revision":"8a6c64fd3948ea484ca0a97f309160b6"},{"url":"static/chunks/1a4h_df1exul_.js","revision":"fc7c39f56fd3e701febbf9a43be62fc7"},{"url":"static/chunks/18wrxbfskdaln.js","revision":"3c14148f8dba1a51142d425c140a71c3"},{"url":"static/chunks/18m5wmv9y6zz-.js","revision":"f42f0aeeab72c2479c82cfd99146b72e"},{"url":"static/chunks/18ao8fnmq17lp.js","revision":"ef733fe6a31c03da44f51437e2909e9d"},{"url":"static/chunks/185wwsgr49vcv.js","revision":"a608a0fd617ef75243b0c22e320a0f1c"},{"url":"static/chunks/185ugu44wc2ps.js","revision":"7c92bddc5f0e5c7966fece4fabf37b5e"},{"url":"static/chunks/181d29m6rjk8_.js","revision":"d4e4274cc609dce7504c3d9020f9dafe"},{"url":"static/chunks/17qww-cmsj2bp.js","revision":"2eda7c9cc304aabce440d6aa382dd7c7"},{"url":"static/chunks/17qlx516otyq3.js","revision":"12a7105415566b1e7a0f6cbd5cc958c7"},{"url":"static/chunks/17p5bpr4jq6nq.js","revision":"e39f55ded8024eb81402119417a3868b"},{"url":"static/chunks/17dpwa3lu_lty.js","revision":"87540f2acb79fe891af20c1dd034c84c"},{"url":"static/chunks/16wohehat-z_q.js","revision":"12c21bad8ed3f17454dd2cb054a7aae6"},{"url":"static/chunks/16n0i8cwk8moq.js","revision":"55627be116394cfdf93d14cccc7aa9ad"},{"url":"static/chunks/168p385jcqmba.js","revision":"1b0ea5b0f3b3b3d76fcfb22e973773ce"},{"url":"static/chunks/167o9xz2k538f.js","revision":"39521c90aab3fd2f7fca5be73e439783"},{"url":"static/chunks/16-zxpzu23uyt.js","revision":"39f8f07df20dfc10e6233634c15afa6b"},{"url":"static/chunks/15jteofh7qsmt.js","revision":"ead433118f25cfce22f982ef406f765e"},{"url":"static/chunks/14s4mo05n6fep.js","revision":"4927222794b455bef2cc32c9c767ac2f"},{"url":"static/chunks/14qp5edd_rdht.js","revision":"99ecb9d92f87150e73d731c69a8d449a"},{"url":"static/chunks/14efqw5n166je.js","revision":"a1655c1fac3e46d6a077439926d961bd"},{"url":"static/chunks/142b47iuq9e3d.js","revision":"c6f2d67cfa4e3f79ff82363b7205a923"},{"url":"static/chunks/13m9pdajvrvac.js","revision":"2bf2cf8aa050777ede6e825ea7e35c4a"},{"url":"static/chunks/13btkpvgxh3bl.js","revision":"d8f6d33b2bdd3a5dfd5067ef12e14c70"},{"url":"static/chunks/12x-1ugk-akb3.js","revision":"e942518cd87d9aab6d02dcdc5a323857"},{"url":"static/chunks/1290u9vl5ybrf.js","revision":"99cd9650a221a3e730780177751a8c90"},{"url":"static/chunks/126_61l1d142q.js","revision":"1a7cc31fb41c6963f796643e835e0cfd"},{"url":"static/chunks/11u79wn132_3i.js","revision":"d7c8525a56c3a61b3f06e48abd3e5a19"},{"url":"static/chunks/11qny5v0r25tq.js","revision":"34c43c82ea337c055e999ceea5e3573b"},{"url":"static/chunks/11mw6se1a3a1b.js","revision":"3fdebc5b7bbca352f69143ad861802d0"},{"url":"static/chunks/11j-mlfcdscz0.js","revision":"baccd9940863ff372e4898073e705ead"},{"url":"static/chunks/11e-yglsu7odg.js","revision":"ca8125338c7f6fefa6fccb66bf316b5e"},{"url":"static/chunks/11_4yeass7tb5.js","revision":"11b27d6729ebbe01ddd4a7199224673a"},{"url":"static/chunks/119mol08fxhzk.js","revision":"ef92960ecd45d49337c62570ae6b0e8c"},{"url":"static/chunks/10qbfjm-1jvw2.js","revision":"339a14fd54431f6ab46e8a8d9ccc577a"},{"url":"static/chunks/107r3u06ttf_k.js","revision":"cf94b1278938c422468124b11e1f05df"},{"url":"static/chunks/101tb7d55ipnl.js","revision":"ba7a5a341bba496bda138b0f74b1f2af"},{"url":"static/chunks/1-f26juzswr0r.js","revision":"bd9ae36f35c007aae8acd4ff250036bf"},{"url":"static/chunks/0zhbd644m9eji.js","revision":"34dcca0e578378350b4444cac63b8c68"},{"url":"static/chunks/0zagyndn2vb6p.js","revision":"9c7beb9d1552bfd59faf1e22556c832c"},{"url":"static/chunks/0yy6odskhkhab.js","revision":"48e8abd7b72df70d8d7660b1ebbaa477"},{"url":"static/chunks/0ywq75qtwm9pt.js","revision":"06197e689d58c4481a479484c668c425"},{"url":"static/chunks/0yag32sm3ubha.js","revision":"b0031f008b842d4f2b61881b60d13e6b"},{"url":"static/chunks/0xys2vg_pgt19.js","revision":"2446a4662e91f2c69676cd1bada458ec"},{"url":"static/chunks/0xn47z7z857cw.js","revision":"004213712b6b6591de1032029b26931b"},{"url":"static/chunks/0xmlxv5spc-7f.js","revision":"8647250592ede0d0b9e71103d63b0c1f"},{"url":"static/chunks/0x4dd1fk94t0q.js","revision":"0648929d99e1d5d0b61b2da2b68422c9"},{"url":"static/chunks/0x4_udjyx_6z-.js","revision":"77a3ce5ee76349231ca82a3cf4992f18"},{"url":"static/chunks/0wpz8sncpt2_5.js","revision":"bb4439be886b34269cd357b102f8708c"},{"url":"static/chunks/0w44_eo3k1nyp.js","revision":"93d2f11556b871b15a5741198b567127"},{"url":"static/chunks/0vkl3weldiay0.js","revision":"7e777671ac704a9344ce177184659a10"},{"url":"static/chunks/0v7vcuc4dorph.js","revision":"25e4adb2c244c828366e049026e65abf"},{"url":"static/chunks/0u5hbe6d-zmem.js","revision":"50af67112d1404a57746c113304ca4b7"},{"url":"static/chunks/0tz_bvu6s-74v.js","revision":"883527d21f1eb3a972bc1b94a344d38d"},{"url":"static/chunks/0tc_oa29p5ft8.js","revision":"d280cf8f7485579f0ac9f82cc77c10fa"},{"url":"static/chunks/0t5v98zz9m8uu.js","revision":"7e646f848d9b7ba3453ae59071398390"},{"url":"static/chunks/0szfqp92x8fmz.js","revision":"334bae8501f6a873203208ca96b61dc5"},{"url":"static/chunks/0sph_z586bvvz.js","revision":"dd61559ddd55b5b3833a55edbe9cbdaf"},{"url":"static/chunks/0sp--t1f-36t6.js","revision":"8c739c45103822402160b420504230b0"},{"url":"static/chunks/0s1zhfko2ue8x.js","revision":"ee8c35ec2792f40dfd80d2bf524610ba"},{"url":"static/chunks/0rwk0c549kdu1.js","revision":"33cb7912e36a832865c8ae4dcc0bd329"},{"url":"static/chunks/0rw0herpip5ge.js","revision":"bb5db24740a11914dcfc4373750791f5"},{"url":"static/chunks/0qp50tm70m579.js","revision":"633e6a87d8bd5dff4892d0e741a00e70"},{"url":"static/chunks/0q6iluaupmx1t.js","revision":"0b21c5e5c99a9c163e3e238e1f04e492"},{"url":"static/chunks/0pvh5b0qjms8n.js","revision":"4a76a42d5e8dfffe415f0a340aabbb33"},{"url":"static/chunks/0psrtf2kvb6h6.js","revision":"0c9c977b8ea33ebb1664df03b504acab"},{"url":"static/chunks/0pf-lzqx2dj2j.js","revision":"b9a810b7b27f5f9171c78ec871a99584"},{"url":"static/chunks/0ooe3mb8-fwmj.js","revision":"8903d6f7e8c5d666fb5b98d6616c3ff4"},{"url":"static/chunks/0of15t5ra4t1u.js","revision":"49e859e1db0610a9e3acecc5714defc1"},{"url":"static/chunks/0o0jgntpj7lcy.js","revision":"415aa6a7b43e59d478cc1aa041ed49c8"},{"url":"static/chunks/0mliximc52drg.js","revision":"85597ee2f781295648d2ec939436576e"},{"url":"static/chunks/0lsus1maqqzsh.js","revision":"1a5812ae319b9303643281d922e46a2a"},{"url":"static/chunks/0krgl29_zghsh.js","revision":"54695771b240bf06c7587c17a2b795e4"},{"url":"static/chunks/0kdcc6n6woios.js","revision":"409a574be5b458a75b1ba1adae8a6aa9"},{"url":"static/chunks/0k3sdwdyzyu1n.js","revision":"8b516ae60d69c64dbfd9a600b7f1aee2"},{"url":"static/chunks/0jr7xnvpojhz8.js","revision":"6aaed3145276a1de363fe6993828f211"},{"url":"static/chunks/0jl6blq2tr6b3.js","revision":"35a87a68c472a49608652316929e0242"},{"url":"static/chunks/0jcpcfg3ac74u.js","revision":"1f6e72d55af4a22a44efb7bc46c2e06f"},{"url":"static/chunks/0ixq0s2ee7ism.js","revision":"a500dd4a3dcd78609f72c1b09e6397ba"},{"url":"static/chunks/0itwg58r-f6uy.js","revision":"48a24d1233ee515704734a6833084448"},{"url":"static/chunks/0ijwrcmpu8c-x.js","revision":"e121cd0d723417a6ce029a2d189802fd"},{"url":"static/chunks/0icjytvdsjvj2.js","revision":"d9037b97b2ce7dc038c9f2b35714970d"},{"url":"static/chunks/0htmz36f7gtcz.js","revision":"83a6d0a9bac4a9e3deeade08fd5b4c51"},{"url":"static/chunks/0h9qp4jn-u95v.js","revision":"cf07caa3f3d0fd178b3f3405c3b078ea"},{"url":"static/chunks/0h1ugwqjvgd5d.js","revision":"90ec2ee0f2440ca0dad5e2ab65e67d89"},{"url":"static/chunks/0grj2idcxxj7b.js","revision":"c8e2ee062eef27b63fe06d645f47f142"},{"url":"static/chunks/0f5n5g7m3j7p1.js","revision":"9c91d10ecfcdb98d35dec4a1a29d10a4"},{"url":"static/chunks/0ele452jt91a1.js","revision":"a93051c318548931aa2963151e760596"},{"url":"static/chunks/0dl6yhptpm4oe.js","revision":"c507fe473d5b32fa82c584d42d0620fc"},{"url":"static/chunks/0d6tk29hne5dg.js","revision":"1d3e89681ca2ca870775a8962b19ffb4"},{"url":"static/chunks/0cz1d0mv5g_q7.js","revision":"846118c33b2c0e922d7b3a7676f81f6f"},{"url":"static/chunks/0co69z2wfd5b2.js","revision":"8055293656cdf8e54df325016f3a52a1"},{"url":"static/chunks/0chqe3jr549ko.js","revision":"35dd8dc96e4fdb400f56dea529902f15"},{"url":"static/chunks/0bzc4cue-blxr.js","revision":"a9ef824445861d2e30ad05a92c2abad7"},{"url":"static/chunks/0bkomci-jnik7.js","revision":"7a3c697a9e187bd403238827b1bb587e"},{"url":"static/chunks/0bgv-a2wg0kqb.js","revision":"de15bb6df6830c21077b85f81aa1242a"},{"url":"static/chunks/0bfyvc5x0t1zk.js","revision":"8ecd9c93f73de541a8cd3a363231fa65"},{"url":"static/chunks/0beh-acmlb6--.js","revision":"61c4a46ad85a7cdd57f6f661c5e4bdc4"},{"url":"static/chunks/0b_j4n43zla81.js","revision":"8b6487d7a0c793bb20d86a3351bd4347"},{"url":"static/chunks/0b0b066-tcww6.js","revision":"a60af4c093c45aa32d75c25448ed56d2"},{"url":"static/chunks/0aya0w_wd2lu0.js","revision":"2a773546dbc95297bf0504b6a9fdbe0e"},{"url":"static/chunks/0aw2b-xxyq0cw.js","revision":"af8217663f7067d87f0f614d1e67f34b"},{"url":"static/chunks/0au83t7x142g1.js","revision":"c8eaa3a2b9a645d9bf5db9fb55eb7aba"},{"url":"static/chunks/0_rd1cr9kzy9g.js","revision":"70bc5289f94ce162e17d5de637a4d9e7"},{"url":"static/chunks/09rtfq93l0gyu.js","revision":"ac82259952b8297da135b0ee2dabe973"},{"url":"static/chunks/09a73o9v_nz9i.js","revision":"4aac4b342a8c0fc3cc557e6f219d4ac2"},{"url":"static/chunks/07jfglwtf2-mc.js","revision":"d7c8ff5ddf91940ad62ef93178d6359c"},{"url":"static/chunks/07ico47tjxra0.js","revision":"c08b16a0405e692685bef8a5304ad31c"},{"url":"static/chunks/07f_85-5873--.js","revision":"1a8c3835192b158735566d83fc51f514"},{"url":"static/chunks/0706o2m-ybodv.js","revision":"55d0e741310ed09093872e7299b5b70e"},{"url":"static/chunks/06yu1t4y4nkhg.js","revision":"d71b3b6606032bd92b547ff36bec7999"},{"url":"static/chunks/06l3htiy6cidm.js","revision":"1864e05bf13741da848197e1bc5ddcdf"},{"url":"static/chunks/06kx_k7w-acgn.js","revision":"57145ba9bda796e572640f7695aeef2c"},{"url":"static/chunks/067zyctm6q35o.js","revision":"e7a58c95c213ece23c1c62c6212134d1"},{"url":"static/chunks/067xv40kfbf-3.js","revision":"d35c9e9e982accdb8118dc266782b33f"},{"url":"static/chunks/04r1_144kw1u5.js","revision":"7eecd113bb5ab7eaa15572fe7865faac"},{"url":"static/chunks/03oltae8hndf0.js","revision":"29856b30d5bf3538fa016b977977cacd"},{"url":"static/chunks/03imnsy7qso2e.js","revision":"1489268af1a2bad152631f0f0b643f72"},{"url":"static/chunks/03ihfgstw5_e5.js","revision":"6e588f6ef9befea3ee26baba57551824"},{"url":"static/chunks/037dgoxlfpslp.js","revision":"fdf999d1f385ecac1e1564cc2fc14b6c"},{"url":"static/chunks/02nlj3vxfrskf.js","revision":"bf4ed5dbaf9504330f08e8e59080d468"},{"url":"static/chunks/02_zgl7d8bj97.js","revision":"34ea598c8436e92cf1c46fac972bb3dc"},{"url":"static/chunks/022l0tli1sp-1.js","revision":"609ee8084102cc3dc79455366630e798"},{"url":"static/chunks/01qfohj46-mfv.js","revision":"cf5f6712954c9baa665013057be5ad6c"},{"url":"static/chunks/00qskiiyl443t.js","revision":"1b07ccc51cfe110dda8ebfc433980497"},{"url":"static/chunks/0-nxhjyrszq66.js","revision":"a0e9494b9af935a80e08299b2db36e77"},{"url":"server/app/workspace.html","revision":"c36cb381c7fb612cf573a8250e6733f6"},{"url":"server/app/work.html","revision":"4ce14e7b4453b77fd521da786c6d8fae"},{"url":"server/app/subscription.html","revision":"49aecc4d15fd7ea1ec3fd1d84bcc35f2"},{"url":"server/app/skill-optimization.html","revision":"4537833aee9d652d91f1ab5a1d399ba5"},{"url":"server/app/settings.html","revision":"2db5916f0d40edf23b2d8326a578858a"},{"url":"server/app/security.html","revision":"2ed0849a67c795ef90b6f9bddefc7855"},{"url":"server/app/research.html","revision":"569affcd505d83b80003333f3e2ad67d"},{"url":"server/app/projects.html","revision":"92a98f1ebedca3482ad4f1e743a5fc41"},{"url":"server/app/pricing.html","revision":"aaf93ae3fa912233bcad4f28c6f3e4ed"},{"url":"server/app/mobile.html","revision":"8e5cbec1e1f7182047b0fcdc8f3e8a31"},{"url":"server/app/library.html","revision":"04d1e40bcff103c390ac3b5be259fe35"},{"url":"server/app/journey.html","revision":"3ab3ac580457ec5fecf3723b9375f2c9"},{"url":"server/app/index.html","revision":"1b38a2d92f8c085ad71526ff7c4322f6"},{"url":"server/app/health.html","revision":"b4092cfb952923fe8efcacfa0a80caf2"},{"url":"server/app/growth.html","revision":"c36cb381c7fb612cf573a8250e6733f6"},{"url":"server/app/eval-lab.html","revision":"a5ebdb0d1f8d65fdce06811b6700be76"},{"url":"server/app/chat.html","revision":"c36cb381c7fb612cf573a8250e6733f6"},{"url":"server/app/brain.html","revision":"fa35e18a4a0a0d494ded64bffcd328eb"},{"url":"server/app/batch-optimization.html","revision":"5070a2ddbbce36dc67c0d3d172a0d634"},{"url":"server/app/audit.html","revision":"a9fc598206309692cbffa41c7f89dc4c"},{"url":"server/app/artifacts.html","revision":"9b7f4f1780d3381094c869b8f3b18294"},{"url":"server/app/agents.html","revision":"901b7e8bf364dc683a679566c01b824a"},{"url":"server/app/_not-found.html","revision":"c0c17c815431b86031c4f5f274ffbb95"},{"url":"server/app/_global-error.html","revision":"bdcebcc0282a3a1103d03cf40a9c94b8"},{"url":"server/app/[chatId].html","revision":"448288861311dde15358b93c9a2afd2e"},{"url":"server/app/settings/[tab].html","revision":"b4092cfb952923fe8efcacfa0a80caf2"},{"url":"server/app/payment/success.html","revision":"7f800d7b3c414d8597b2d25f81d68286"},{"url":"server/app/payment/cancel.html","revision":"4ae0a214efdb30d3fd12328f34997cd8"},{"url":"server/app/mobile/status/[chatId].html","revision":"c36cb381c7fb612cf573a8250e6733f6"},{"url":"server/app/batch-optimization/[batchId].html","revision":"cafdc0b5991ec1ac5f4165cab9765bab"},{"url":"server/app/auth/setup.html","revision":"f386a0c153070c291f9d9f8229f9e5c1"},{"url":"server/app/auth/login.html","revision":"08b86d6009eb6e7e3002128e720afc52"},{"url":"server/app/auth/oauth/callback.html","revision":"36cae082cf946e7f065f5de55a5ead76"}],
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
  if (!event.data) return;
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
