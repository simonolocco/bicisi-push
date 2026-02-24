module.exports = {
    apps: [
        {
            name: 'bicisi-bot',
            script: 'webhook.py',
            interpreter: 'python',
            env: {
                FLASK_ENV: 'production'
            }
        },
        {
            name: 'bicisi-web',
            script: 'app.py',
            cwd: './reservas',
            interpreter: 'C:\\Python313\\python.exe',
            env: {
                FLASK_ENV: 'production'
            }
        }
    ]
};
