import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True


# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    # SQL query into stocks and then that data in a variable in the return

    # Get stocks table with newest summaries
    stocks = db.execute("SELECT * FROM stocks WHERE user_id = ?", session["user_id"])

    overall_holdings = 0
    for entry in stocks:
        symbol = entry['symbol']
        # get current values
        dict = lookup(symbol)
        current_price = dict['price']
        current_holding = (current_price * entry['shares'])
        overall_holdings += current_holding

        # update all current prices for the stocks
        db.execute("UPDATE stocks SET current_price = ? WHERE id = ? AND symbol = ?", current_price, session["user_id"], symbol)
        db.execute("UPDATE stocks SET value_holding = ? WHERE id = ? AND symbol = ?", current_holding, session["user_id"], symbol)

    # reload stocks to pass on
    all_stocks = db.execute("SELECT * FROM stocks WHERE user_id = ?", session["user_id"])

    # cash
    current_cash = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])
    current_cash_1 = current_cash[0]['cash']
    current_cash_value = usd(float(current_cash_1))

    # grand total
    grand_total1 = 0
    grand_total1 += current_cash[0]['cash']
    grand_total1 += overall_holdings
    grand_total = usd(float(grand_total1))

    return render_template("index.html", stocks=all_stocks, current_cash=current_cash_value, grand_total=grand_total)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    if request.method == "POST":

        # get variables from form

        # get symbol and store in dict
        dict = lookup(request.form.get("symbol"))
        symbol = request.form.get("symbol").upper()

        # check if dict exists
        if dict == None:
            return apology("Stock does not exist.", 400)

        try:
            shares = int(request.form.get("shares"))
        except ValueError:
            return apology("shares must be a positive integer", 400)

        # check if number entered was positive
        share_count = int(float(request.form.get("shares")))

        if share_count < 1:
            return apology("Shares are not positive integer.", 400)

        elif share_count % 1 != 0:
            return apology("number is not a whole number.", 400)

        # check variables with SQL

        # check if user has enough money to buy
        current_money = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])
        if len(current_money) != 1:
            return apology("something went wrong!", 400)

        price_to_buy = (dict['price'] * share_count)

        if price_to_buy > current_money[0]['cash']:
            return apology("You don't have enough money!", 400)

        # SQL query to insert new data on bought stock
        else:
            # calculate new cash value
            new_cash = (current_money[0]['cash'] - price_to_buy)

            # update in users table
            db.execute("UPDATE users SET cash = ? WHERE id = ?", new_cash, session["user_id"])

            # update transactions table
            db.execute("INSERT into transactions (user_id, symbol, name, price_bs, current_price, shares, current_total, bs) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                       session["user_id"], symbol, dict['name'], dict['price'], dict['price'], share_count, price_to_buy, "buy")

            # update stocks table
            # check if stock already exists FOR THIS USER in stocks table
            returns = db.execute("SELECT * FROM stocks WHERE symbol = ? AND user_id = ?", symbol, session["user_id"])
            if len(returns) == 0:
                # create new entry for new stock
                db.execute("INSERT INTO stocks (name, symbol, current_price, shares, value_holding, user_id) VALUES (?, ?, ?, ?, ?, ?)",
                           dict['name'], symbol, dict['price'], share_count, price_to_buy, session["user_id"])

            else:
                # update current price
                db.execute("UPDATE stocks SET current_price = ? WHERE symbol = ? AND user_id = ?",
                           dict['price'], symbol, session["user_id"])

                # get all info for this stock for the user
                entry = db.execute("SELECT * FROM stocks WHERE symbol = ? AND user_id = ?", symbol, session["user_id"])

                # update shares
                new_shares = entry[0]['shares'] + share_count
                db.execute("UPDATE stocks SET shares = ? WHERE symbol = ? AND user_id = ?", new_shares, symbol, session["user_id"])

                # update value_holding
                new_holding = entry[0]['value_holding'] + price_to_buy
                db.execute("UPDATE stocks SET value_holding = ? WHERE symbol = ? AND user_id = ?",
                           new_holding, symbol, session["user_id"])

        return redirect("/")

    if request.method == "GET":
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    # SQL query into stocks and then that data in a variable in the return
    transactions_rows = db.execute("SELECT * FROM transactions WHERE user_id = ?", session["user_id"])

    for entry in transactions_rows:
        symbol = entry['symbol']
        dict = lookup(symbol)
        # get current price
        current_price = dict['price']
        # add up holdings
        current_price_sum = (current_price * entry['shares'])

        # update all current prices for the stocks
        db.execute("UPDATE transactions SET current_price = ? WHERE id = ? AND symbol = ?",
                   current_price, session["user_id"], symbol)
        db.execute("UPDATE transactions SET current_total = ? WHERE id = ? AND symbol = ?",
                   current_price_sum, session["user_id"], symbol)

    # reload transactions
    transactions = db.execute("SELECT * FROM transactions WHERE user_id = ?", session["user_id"])

    return render_template("history.html", transactions=transactions)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""

    if request.method == "POST":

        if not request.form.get("symbol"):
            return apology("No stock symbol entered.", 400)

        symbol = request.form.get("symbol")
        symbol_pass = symbol.upper()

        # get dictionary back for all stock properties
        dict = lookup(symbol)

        if dict == None:
            return apology("Stock does not exist.", 400)

        return render_template("quoted.html", dict=dict, symbol=symbol_pass)

    if request.method == "GET":
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)

        # Ensure passwords match
        elif request.form.get("password") != request.form.get("confirmation"):
            return apology("Passwords do not match", 400)

        username = request.form.get("username")

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", username)

        if len(rows) != 0:
            return apology("Username already exists.", 400)

        # hash password to store in db rather than actual password
        hash = generate_password_hash(request.form.get("password"))

        db.execute("INSERT into users (username, hash) VALUES(?,?)", username, hash)

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    if request.method == "POST":

        # get values from form
        symbol = request.form.get("symbol")
        count1 = request.form.get("shares")
        count = int(float(count1))

        # check if stock in stocks
        stocks = db.execute("SELECT * FROM stocks WHERE symbol = ? AND user_id = ?", symbol, session["user_id"])
        if len(stocks) != 1:
            return apology("You don't have stocks for this company.", 400)

        # check if person has enough stocks to sell
        owned_stocks = stocks[0]['shares']
        if count > owned_stocks:
            return apology("you don't own this many stocks.", 400)

        # if all good, sell stocks at current price
        dict = lookup(symbol)
        current_price = dict['price']

        total_money = current_price * count

        count_entry = count - (count * 2)

        # update transactions table
        db.execute("INSERT into transactions (user_id, symbol, name, price_bs, current_price, shares, current_total, bs) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                   session["user_id"], symbol, dict['name'], dict['price'], dict['price'], count_entry, total_money, "sell")

        # update stocks table
        db.execute("UPDATE stocks SET current_price = ? WHERE symbol = ? AND user_id = ?",
                   dict['price'], symbol, session["user_id"])

        # get all info for this stock for the user
        entry = db.execute("SELECT * FROM stocks WHERE symbol = ? AND user_id = ?", symbol, session["user_id"])

        # update shares
        new_shares = entry[0]['shares'] - count
        db.execute("UPDATE stocks SET shares = ? WHERE symbol = ? AND user_id = ?", new_shares, symbol, session["user_id"])

        # update value_holding
        new_holding = entry[0]['value_holding'] - total_money
        db.execute("UPDATE stocks SET value_holding = ? WHERE symbol = ? AND user_id = ?", new_holding, symbol, session["user_id"])

        # update cash balance in users
        user = db.execute("SELECT * FROM users WHERE id = ?", session["user_id"])
        new_cash = user[0]['cash'] + total_money
        db.execute("UPDATE users SET cash = ? WHERE id = ?", new_cash, session["user_id"])

        return redirect("/")

    if request.method == "GET":
        stocks = db.execute("SELECT * FROM stocks WHERE user_id = ?", session["user_id"])
        return render_template("sell.html", stocks=stocks)


@app.route("/topup", methods=["GET", "POST"])
@login_required
def topup():
    """Sell shares of stock"""

    if request.method == "POST":
        amount = int(request.form.get("amount"))
        if amount < 1:
            return apology("You didn't enter a valid amount.", 400)

        # get current cash
        user = db.execute("SELECT * FROM users WHERE id = ?", session["user_id"])
        current = user[0]['cash']

        new_cash = current + amount

        db.execute("UPDATE users SET cash = ? WHERE id = ?", new_cash, session["user_id"])

        return redirect("/")

    if request.method == "GET":

        return render_template("topup.html")


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
