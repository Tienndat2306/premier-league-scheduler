from app import create_app

app = create_app()

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  PREMIER LEAGUE SCHEDULER STARTING")
    print("  Server running at: http://localhost:5000")
    print("=" * 60 + "\n")
    app.run(debug=True, port=5000, use_reloader=False)
