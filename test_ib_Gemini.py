from ib_insync import *

# 1. Créer une instance de l'API
ib = IB()

try:
    # 2. Se connecter au port du Trading Simulé (7497 par défaut)
    # '127.0.0.1' correspond à votre propre ordinateur (localhost)
    ib.connect('127.0.0.1', 7497, clientId=1)

    if ib.isConnected():
        print("✅ Connexion réussie à IBKR !")
        
        # 3. Récupérer les informations de compte
        account_values = ib.accountValues()
        print(f"--- Détails du compte ---")
        for val in account_values:
            if val.tag == 'NetLiquidation':
                print(f"Valeur nette du compte (Simulé) : {val.value} {val.currency}")
        
        # 4. Tester la réception du prix EUR/USD
        contract = Forex('EURUSD')
        ib.qualifyContracts(contract)
        ticker = ib.reqMktData(contract)
        
        print("Récupération du prix en cours...")
        ib.sleep(2) # Attendre 2 secondes pour recevoir les données
        print(f"Prix actuel EUR/USD : {ticker.marketPrice()}")

    else:
        print("❌ Échec de la connexion. Vérifiez que IB Gateway est ouvert.")

except Exception as e:
    print(f"⚠️ Une erreur est survenue : {e}")

finally:
    # Toujours se déconnecter proprement à la fin
    ib.disconnect()
    print("Déconnecté.")
