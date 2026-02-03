/**
 * Frontend Error Reporter for CAIO Dashboard
 * ==========================================
 *
 * Captures and reports frontend errors to the backend for correlation
 * with backend failures via the debug-mcp server.
 *
 * Usage: Include this script in your HTML:
 *   <script src="/static/error-reporter.js"></script>
 *
 * Or initialize manually:
 *   CAIOErrorReporter.init({ endpoint: '/api/errors/frontend' });
 */

(function(window) {
    'use strict';

    const CAIOErrorReporter = {
        config: {
            endpoint: '/api/errors/frontend',
            correlationIdEndpoint: '/api/debug/correlation-id',
            maxErrors: 100,       // Max errors to track per session
            debounceMs: 100,      // Debounce rapid-fire errors
            enabled: true
        },

        // State
        _errorCount: 0,
        _correlationId: null,
        _lastError: null,
        _lastErrorTime: 0,

        /**
         * Initialize the error reporter
         */
        init: function(options) {
            Object.assign(this.config, options || {});

            if (!this.config.enabled) return;

            // Fetch correlation ID from server
            this._fetchCorrelationId();

            // Set up global error handlers
            this._setupErrorHandlers();

            console.log('[CAIOErrorReporter] Initialized');
        },

        /**
         * Fetch correlation ID from the server
         */
        _fetchCorrelationId: async function() {
            try {
                const response = await fetch(this.config.correlationIdEndpoint);
                const data = await response.json();
                this._correlationId = data.correlation_id;

                // Store in meta tag for other scripts to access
                let meta = document.querySelector('meta[name="correlation-id"]');
                if (!meta) {
                    meta = document.createElement('meta');
                    meta.name = 'correlation-id';
                    document.head.appendChild(meta);
                }
                meta.content = this._correlationId;

            } catch (e) {
                console.warn('[CAIOErrorReporter] Failed to fetch correlation ID:', e);
            }
        },

        /**
         * Set up all error handlers
         */
        _setupErrorHandlers: function() {
            const self = this;

            // Global error handler (uncaught errors)
            window.addEventListener('error', function(event) {
                self.reportError({
                    message: event.message,
                    stack: event.error?.stack,
                    url: event.filename,
                    line: event.lineno,
                    column: event.colno,
                    type: 'error'
                });
            });

            // Unhandled promise rejections
            window.addEventListener('unhandledrejection', function(event) {
                self.reportError({
                    message: 'Unhandled Promise Rejection: ' + String(event.reason),
                    stack: event.reason?.stack,
                    type: 'exception'
                });
            });

            // Console error override
            const originalConsoleError = console.error;
            console.error = function(...args) {
                originalConsoleError.apply(console, args);

                const message = args.map(arg => {
                    if (arg instanceof Error) return arg.message;
                    if (typeof arg === 'object') return JSON.stringify(arg);
                    return String(arg);
                }).join(' ');

                self.reportError({
                    message: message,
                    stack: args.find(a => a instanceof Error)?.stack,
                    type: 'error'
                });
            };

            // Console warn override (optional - for tracking warnings)
            const originalConsoleWarn = console.warn;
            console.warn = function(...args) {
                originalConsoleWarn.apply(console, args);

                const message = args.map(arg => {
                    if (typeof arg === 'object') return JSON.stringify(arg);
                    return String(arg);
                }).join(' ');

                self.reportError({
                    message: message,
                    type: 'warning'
                });
            };
        },

        /**
         * Report an error to the backend
         */
        reportError: async function(errorData) {
            if (!this.config.enabled) return;

            // Rate limiting
            if (this._errorCount >= this.config.maxErrors) {
                return;
            }

            // Debounce duplicate errors
            const now = Date.now();
            if (errorData.message === this._lastError &&
                now - this._lastErrorTime < this.config.debounceMs) {
                return;
            }
            this._lastError = errorData.message;
            this._lastErrorTime = now;

            // Build payload
            const payload = {
                message: errorData.message || 'Unknown error',
                stack: errorData.stack,
                url: errorData.url || window.location.href,
                type: errorData.type || 'error',
                user_agent: navigator.userAgent,
                line: errorData.line,
                column: errorData.column,
                timestamp: new Date().toISOString()
            };

            this._errorCount++;

            try {
                const headers = {
                    'Content-Type': 'application/json'
                };

                // Add correlation ID if available
                if (this._correlationId) {
                    headers['X-Correlation-ID'] = this._correlationId;
                }

                await fetch(this.config.endpoint, {
                    method: 'POST',
                    headers: headers,
                    body: JSON.stringify(payload)
                });

            } catch (e) {
                // Don't use console.error to avoid infinite loop
                if (window.__originalConsoleError) {
                    window.__originalConsoleError('[CAIOErrorReporter] Failed to report error:', e);
                }
            }
        },

        /**
         * Manually report an error
         */
        report: function(message, extra) {
            this.reportError({
                message: message,
                type: 'error',
                ...extra
            });
        },

        /**
         * Get current correlation ID
         */
        getCorrelationId: function() {
            return this._correlationId;
        },

        /**
         * Enable/disable reporting
         */
        setEnabled: function(enabled) {
            this.config.enabled = enabled;
        }
    };

    // Store original console.error for internal use
    window.__originalConsoleError = console.error;

    // Auto-initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            CAIOErrorReporter.init();
        });
    } else {
        CAIOErrorReporter.init();
    }

    // Expose globally
    window.CAIOErrorReporter = CAIOErrorReporter;

})(window);
