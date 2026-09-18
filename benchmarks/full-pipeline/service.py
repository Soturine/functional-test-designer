def confirm(reservation):
    reservation.state = "REVIEWED"  # observed implementation diverges from the approved requirement


def cancel(reservation):
    reservation.state = "CANCELLED"
