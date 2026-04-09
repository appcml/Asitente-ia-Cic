@app.route('/create-emergency-admin')
def create_emergency_admin():
    """Crear admin de emergencia - eliminar después de usar"""
    try:
        # Crear en ambas tablas
        admin_user = UserAccount.query.filter_by(username='emergency').first()
        if not admin_user:
            admin_user = UserAccount(
                username='emergency',
                email='emergency@dev.local',
                personality_mode='kimi'
            )
            admin_user.set_password('Emergency123!')
            db.session.add(admin_user)
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': 'Usuario de emergencia creado',
                'credentials': {
                    'username': 'emergency',
                    'password': 'Emergency123!'
                },
                'note': 'Usar en /login (no /dev-login)'
            })
        else:
            return jsonify({
                'message': 'Usuario emergency ya existe',
                'credentials': {
                    'username': 'emergency',
                    'password': 'Emergency123!'
                }
            })
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500
