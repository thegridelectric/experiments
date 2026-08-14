%% GridWorks SASL mechanism (OPS-496; design: OPS-420 "The mechanism plugin").
%% Two-change fork of stock rabbit_auth_mechanism_ssl, which derives the
%% username from the peer cert, IGNORES the SASL response bytes, and passes
%% AuthProps = []. This module keeps the cert identity exactly and:
%%   1. treats the SASL response bytes as the claims payload (opaque here);
%%   2. passes them as AuthProps [{claims, Response}], which the stock http
%%      auth backend forwards verbatim to FIS.
%% The plugin never parses the payload: claim evolution is a sema word
%% version, not a plugin rebuild.

-module(rabbit_auth_mechanism_gridworks).

-behaviour(rabbit_auth_mechanism).

-export([description/0, should_offer/1, init/1, handle_response/2]).

-rabbit_boot_step(
   {?MODULE,
    [{description, "auth mechanism gridworks (cert identity + claims)"},
     {mfa, {rabbit_registry, register,
            [auth_mechanism, <<"GRIDWORKS">>, ?MODULE]}},
     {requires, rabbit_registry},
     {enables, kernel_ready}]}).

-record(state, {username = undefined}).

description() ->
    [{description, <<"GridWorks: x509 certificate identity plus a "
                     "connect-claims payload in the SASL response, "
                     "forwarded to FIS via auth_backend_http">>}].

%% Offer only on TLS sockets that presented a verified peer cert.
should_offer(Sock) ->
    case rabbit_net:peercert(Sock) of
        {ok, _}              -> true;
        nossl                -> false;
        {error, no_peercert} -> false
    end.

%% Derive the username (= principal id: GNodeId / principal UUID) from the
%% cert, exactly as stock does; honors ssl_cert_login_from.
init(Sock) ->
    Username = case rabbit_net:peercert(Sock) of
                   {ok, C} ->
                       case rabbit_ssl:peer_cert_auth_name(C) of
                           unsafe    -> {refused, none,
                                         "TLS configuration is unsafe", []};
                           not_found -> {refused, none,
                                         "no name found in certificate", []};
                           Name      -> rabbit_data_coercion:to_binary(Name)
                       end;
                   {error, no_peercert} ->
                       {refused, none,
                        "connection peer presented no TLS certificate", []};
                   nossl ->
                       {refused, none, "not a TLS connection", []}
               end,
    #state{username = Username}.

%% Response = the client's SASL response bytes: the fis.connect.claims sema
%% word as serialized JSON, passed through OPAQUE. Empty/absent claims are
%% FIS's to judge — policy stays out of the plugin.
handle_response(_Response, #state{username = {refused, _, _, _} = E}) ->
    E;
handle_response(Response, #state{username = Username}) ->
    rabbit_access_control:check_user_login(Username, [{claims, Response}]).
